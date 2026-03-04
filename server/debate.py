from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from openai import OpenAI

from .prompts import CAESAR_SYSTEM_PROMPT, POMPEY_SYSTEM_PROMPT
from .rag import RAG


@dataclass
class DebateState:
    conversation_id: str
    topic: str
    started_at: float
    stop_requested: bool = False
    active: bool = True
    turns: List[str] = field(default_factory=list)
    history_caesar: List[dict] = field(default_factory=list)
    history_pompey: List[dict] = field(default_factory=list)
    agenda: Optional[str] = None
    queue: Optional[asyncio.Queue] = None
    worker: Optional[asyncio.Task] = None


class DebateManager:
    def __init__(
        self,
        rag: RAG,
        openai_client: OpenAI,
        model: str,
        max_seconds: int = 180,
        max_turns: int = 12,
        turn_delay_seconds: float = 0.6,
    ):
        self.rag = rag
        self.openai_client = openai_client
        self.model = model
        self.max_seconds = max_seconds
        self.max_turns = max_turns
        self.turn_delay_seconds = turn_delay_seconds
        self.states: Dict[str, DebateState] = {}

    def is_active(self, conversation_id: str) -> bool:
        state = self.states.get(conversation_id)
        return bool(state and state.active)

    def get_state(self, conversation_id: str) -> Optional[DebateState]:
        return self.states.get(conversation_id)

    async def start_debate(self, conversation_id: str, topic: str) -> DebateState:
        existing = self.states.get(conversation_id)
        if existing and existing.active:
            existing.stop_requested = True
            if existing.worker:
                await asyncio.sleep(0.1)

        queue: asyncio.Queue = asyncio.Queue()
        state = DebateState(
            conversation_id=conversation_id,
            topic=topic,
            started_at=time.time(),
            queue=queue,
        )
        self.states[conversation_id] = state
        state.worker = asyncio.create_task(self.debate_worker(conversation_id))
        return state

    def stop_debate(self, conversation_id: str) -> bool:
        state = self.states.get(conversation_id)
        if not state or not state.active:
            return False
        state.stop_requested = True
        return True

    def update_agenda(self, conversation_id: str, agenda: str) -> bool:
        state = self.states.get(conversation_id)
        if not state or not state.active:
            return False
        state.agenda = agenda
        return True

    async def debate_worker(self, conversation_id: str) -> None:
        state = self.states[conversation_id]
        speakers = ["Caesar", "Pompey"]

        for turn_index in range(self.max_turns):
            if state.stop_requested:
                break
            if (time.time() - state.started_at) > self.max_seconds:
                break

            speaker = speakers[turn_index % 2]
            text = self._generate_turn(state, speaker)
            line = f"**{speaker}:** {text}"
            state.turns.append(line)
            if state.queue:
                await state.queue.put(line)

            await asyncio.sleep(self.turn_delay_seconds)

        state.active = False
        if state.queue:
            await state.queue.put("[DEBATE_DONE]")

    def _generate_turn(self, state: DebateState, speaker: str) -> str:
        collection = "caesar_collection" if speaker == "Caesar" else "pompey_collection"
        system_prompt = CAESAR_SYSTEM_PROMPT if speaker == "Caesar" else POMPEY_SYSTEM_PROMPT
        agent_history = state.history_caesar if speaker == "Caesar" else state.history_pompey

        current_question = state.agenda or state.topic
        snippets = self.rag.retrieve(collection, current_question, k=4)
        context_text = "\n\n".join(
            [f"[{i+1}] ({s['source']}) {s['text']}" for i, s in enumerate(snippets)]
        )
        source_names = sorted(set(s["source"] for s in snippets)) or ["none"]

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Debate topic: {state.topic}\n"
                    f"Current agenda: {current_question}\n\n"
                    f"Retrieved snippets (ONLY usable facts):\n{context_text or 'No snippets found.'}\n\n"
                    "Produce one short turn (4-8 sentences). End with a single line: "
                    f"Sources: {', '.join(source_names)}"
                ),
            },
        ] + agent_history[-6:]

        completion = self.openai_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
        )
        content = completion.choices[0].message.content or "Not supported by sources.\nSources: none"

        agent_history.append({"role": "assistant", "content": content})
        return content
