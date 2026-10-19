from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from .prompts import CAESAR_SYSTEM_PROMPT, POMPEY_SYSTEM_PROMPT
from .rag import RAG, Snippet

LOG_DIR = Path(os.getenv("DEBATE_LOG_DIR", "./logs"))
LOG_PATH = LOG_DIR / "debate.log"

# (speaker name, chroma collection, system prompt)
SPEAKERS = [
    ("Caesar", "caesar_collection", CAESAR_SYSTEM_PROMPT),
    ("Pompey", "pompey_collection", POMPEY_SYSTEM_PROMPT),
]

# How many past turns are replayed to the model on each turn.
HISTORY_TURNS = 40


def _make_debate_logger(topic: str) -> logging.Logger:
    """Start a fresh logs/debate.log for this debate."""
    LOG_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger("debate")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        h.close()
    fh = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(fh)
    logger.info("DEBATE START  topic=%s", topic)
    return logger


def build_retrieval_query(topic: str, turns: list[tuple[str, str]]) -> str:
    """Query for the vector search: the topic plus the start of the opponent's last turn.

    Only the first ~200 chars of the last turn are used. Embedding a whole speech
    dilutes the query and pulls in less relevant chunks.
    """
    if not turns:
        return f"Topic: {topic}"
    last = turns[-1][1][:200].rsplit(" ", 1)[0] + "…"
    return f"Topic: {topic}\nOpponent's last point we need to rebut: {last}"


def build_documents_block(snippets: list[Snippet]) -> str:
    if not snippets:
        return "<documents>\n  <empty/>\n</documents>"
    lines = ["<documents>"]
    for i, s in enumerate(snippets, start=1):
        lines.append(f'  <document index="{i}">')
        lines.append(f"    <source>{s['source']}</source>")
        lines.append(f"    <document_content>{s['text']}</document_content>")
        lines.append("  </document>")
    lines.append("</documents>")
    return "\n".join(lines)


def build_messages(
    speaker: str,
    system_prompt: str,
    topic: str,
    turns: list[tuple[str, str]],
    snippets: list[Snippet],
) -> list[ChatCompletionMessageParam]:
    """Build the chat request for one turn, from the point of view of `speaker`.

    The speaker's own past turns become "assistant" messages and the opponent's
    become "user" messages, so each agent only ever sees the debate from its own
    side. Retrieved documents go into the last user message, before the
    instruction, rather than into the system prompt. That keeps the system prompt
    identical across turns and puts the sources right next to the question.
    """
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": f"{system_prompt}\n\n<debate_topic>{topic}</debate_topic>"},
    ]

    for name, text in turns[-HISTORY_TURNS:]:
        role = "assistant" if name == speaker else "user"
        messages.append({"role": role, "content": text})

    if turns:
        opponent = "Pompey" if speaker == "Caesar" else "Caesar"
        task = f"Now respond to {opponent}'s latest argument."
    else:
        task = f"Open the debate on: {topic}"

    messages.append(
        {
            "role": "user",
            "content": (
                f"{build_documents_block(snippets)}\n\n"
                "Above are retrieved historical sources for this turn. "
                "Cite relevant documents as [1], [2] etc. for concrete factual claims. "
                f"{task}"
            ),
        }
    )
    return messages


@dataclass
class DebateState:
    topic: str
    started_at: float
    log: logging.Logger
    stop_requested: bool = False
    active: bool = True
    turns: list[tuple[str, str]] = field(default_factory=list)  # (speaker, text)
    queue: asyncio.Queue | None = None
    worker: asyncio.Task | None = None


class DebateManager:
    """Runs debates in the background and streams tokens through a per-debate queue.

    Besides model tokens the queue carries a few control markers the UI relies on:
    [START:<speaker>], [END_TURN], [ERROR] <message> and [DEBATE_DONE].
    """

    def __init__(
        self,
        rag: RAG,
        openai_client: OpenAI,
        model: str,
        max_turns: int = 30,
        turn_delay: float = 0.5,
    ):
        self.rag = rag
        self.client = openai_client
        self.model = model
        self.max_turns = max_turns
        self.turn_delay = turn_delay
        self.retrieval_k = int(os.getenv("RAG_RETRIEVAL_K", "14"))
        # Temperature is only sent when set explicitly, because reasoning models reject it.
        temperature = os.getenv("LLM_TEMPERATURE", "")
        self._extra_kwargs: dict = {"temperature": float(temperature)} if temperature else {}
        self.states: dict[str, DebateState] = {}

    def is_active(self, cid: str) -> bool:
        s = self.states.get(cid)
        return bool(s and s.active)

    def get_state(self, cid: str) -> DebateState | None:
        return self.states.get(cid)

    async def start_debate(self, cid: str, topic: str) -> DebateState:
        old = self.states.get(cid)
        if old and old.active:
            old.stop_requested = True
            await asyncio.sleep(0.1)

        state = DebateState(
            topic=topic,
            started_at=time.time(),
            log=_make_debate_logger(topic),
            queue=asyncio.Queue(),
        )
        self.states[cid] = state
        state.worker = asyncio.create_task(self._run_debate(state))
        return state

    def stop_debate(self, cid: str) -> bool:
        s = self.states.get(cid)
        if not s or not s.active:
            return False
        s.stop_requested = True
        return True

    async def _run_debate(self, state: DebateState) -> None:
        loop = asyncio.get_running_loop()
        try:
            for i in range(self.max_turns):
                if state.stop_requested:
                    break
                name, collection, system = SPEAKERS[i % 2]
                # The OpenAI client is synchronous, so each turn runs in a worker thread.
                text = await asyncio.to_thread(
                    self._generate_turn,
                    state,
                    name,
                    collection,
                    system,
                    loop,
                )
                state.turns.append((name, text))
                await asyncio.sleep(self.turn_delay)
        except Exception as exc:  # noqa: BLE001 - any failure should end the debate and reach the UI
            if state.queue:
                await state.queue.put(f"[ERROR] {exc}")
        finally:
            state.active = False
            state.log.info("DEBATE END  turns=%d  elapsed=%.1fs", len(state.turns), time.time() - state.started_at)
            if state.queue:
                await state.queue.put("[DEBATE_DONE]")

    def _generate_turn(
        self,
        state: DebateState,
        speaker: str,
        collection: str,
        system_prompt: str,
        loop: asyncio.AbstractEventLoop,
    ) -> str:
        query = build_retrieval_query(state.topic, state.turns)
        snippets = self.rag.retrieve(collection, query, k=self.retrieval_k)
        messages = build_messages(speaker, system_prompt, state.topic, state.turns, snippets)

        if state.queue:
            loop.call_soon_threadsafe(state.queue.put_nowait, f"[START:{speaker}]")

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            **self._extra_kwargs,
        )
        parts: list[str] = []
        try:
            for chunk in stream:
                if state.stop_requested:
                    break
                # Some OpenAI-compatible servers send chunks with no choices (e.g. usage stats).
                if not chunk.choices:
                    continue
                token = chunk.choices[0].delta.content or ""
                if token:
                    parts.append(token)
                    if state.queue:
                        loop.call_soon_threadsafe(state.queue.put_nowait, token)
        finally:
            stream.close()

        response = "".join(parts) or "Not supported by sources."

        # The log keeps the retrieved chunks next to each answer, which makes it
        # easy to check whether a citation actually matches its source.
        turn_num = len(state.turns) + 1
        state.log.info("-- TURN %d: %s --", turn_num, speaker)
        for i, s in enumerate(snippets, start=1):
            state.log.info("  chunk[%d] (%s):\n%s", i, s["source"], s["text"])
        state.log.info("  RESPONSE: %s", response)

        if state.queue:
            loop.call_soon_threadsafe(state.queue.put_nowait, "[END_TURN]")

        return response
