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
from .rag import RAG

LOG_DIR = Path(os.getenv("DEBATE_LOG_DIR", "./logs"))
LOG_PATH = LOG_DIR / "debate.log"

# (speaker name, chroma collection, system prompt)
SPEAKERS = [
    ("Caesar", "caesar_collection", CAESAR_SYSTEM_PROMPT),
    ("Pompey", "pompey_collection", POMPEY_SYSTEM_PROMPT),
]


def _make_debate_logger(topic: str) -> logging.Logger:
    """Create (or reset) the debate log file."""
    LOG_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger("debate")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    # Remove old handlers, start fresh file
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        h.close()
    fh = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(fh)
    logger.info("DEBATE START  topic=%s", topic)
    return logger


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
        # Only pass temperature if explicitly set (reasoning models reject it)
        _t = os.getenv("LLM_TEMPERATURE", "")
        self._extra_kwargs: dict = {"temperature": float(_t)} if _t else {}
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
            topic=topic, started_at=time.time(),
            log=_make_debate_logger(topic), queue=asyncio.Queue(),
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

    # ── debate loop ──────────────────────────────────────────────

    async def _run_debate(self, state: DebateState) -> None:
        loop = asyncio.get_running_loop()
        try:
            for i in range(self.max_turns):
                if state.stop_requested:
                    break
                name, collection, system = SPEAKERS[i % 2]
                text = await asyncio.to_thread(
                    self._generate_turn, state, name, collection, system, loop,
                )
                state.turns.append((name, text))
                await asyncio.sleep(self.turn_delay)
        except Exception as exc:
            if state.queue:
                await state.queue.put(f"[ERROR] {exc}")
        finally:
            state.active = False
            state.log.info("DEBATE END  turns=%d  elapsed=%.1fs", len(state.turns), time.time() - state.started_at)
            if state.queue:
                await state.queue.put("[DEBATE_DONE]")

    # ── single turn generation ───────────────────────────────────

    def _generate_turn(
        self,
        state: DebateState,
        speaker: str,
        collection: str,
        system_prompt: str,
        loop: asyncio.AbstractEventLoop,
    ) -> str:
        # Retrieve relevant snippets — structured query, truncated for embedding quality
        if state.turns:
            last = state.turns[-1][1][:200].rsplit(" ", 1)[0] + "…"
            query = f"Topic: {state.topic}\nOpponent's last point we need to rebuttal: {last}"
        else:
            query = f"Topic: {state.topic}"
        snippets = self.rag.retrieve(collection, query, k=self.retrieval_k)

        snippet_block = "\n".join(
            f'<snippet id="{i+1}" source="{s["source"]}">{s["text"]}</snippet>'
            for i, s in enumerate(snippets)
        )

        # Build messages: system → context → instructions → conversation history
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "system",
                "content": (
                    "<snippets>\n"
                    + (snippet_block or "<empty/>")
                    + "\n</snippets>\n"
                    "Cite as [1], [2] etc. when a snippet supports a factual claim."
                ),
            },
            {
                "role": "system",
                "content": (
                    f"Debate topic: {state.topic}\n\n"
                    "INSTRUCTIONS:\n"
                    "- Your response MUST be about the debate topic above.\n"
                    "- Speak in first person as this Roman statesman.\n"
                    "- Sentence 1: directly rebut the opponent's latest claim.\n"
                    "- Then 3-7 more sentences: your strongest argument.\n"
                    "- Be forceful, adversarial, and in character.\n"
                    "- Do NOT repeat arguments already made.\n"
                    "- If no snippets are relevant, argue from character knowledge.\n"
                    "- Do not invent precise facts.\n"
                    "- If you cited snippets, end with: Sources: filename.txt [1][3], other.txt [2]."
                ),
            },
        ]

        # Replay past turns as alternating user/assistant messages.
        # Own turns → assistant, opponent turns → user.
        # Keep only last 40 turns to limit context length.
        recent_turns = state.turns[-40:] if len(state.turns) > 40 else state.turns
        for name, text in recent_turns:
            if name == speaker:
                messages.append({"role": "assistant", "content": text})
            else:
                messages.append({"role": "user", "content": text})

        # Signal turn start
        if state.queue:
            loop.call_soon_threadsafe(state.queue.put_nowait, f"[START:{speaker}]")

        stream = self.client.chat.completions.create(
            model=self.model, messages=messages, stream=True, **self._extra_kwargs,
        )
        parts: list[str] = []
        for chunk in stream:
            token = chunk.choices[0].delta.content or ""
            if token:
                parts.append(token)
                if state.queue:
                    loop.call_soon_threadsafe(state.queue.put_nowait, token)

        response = "".join(parts) or "Not supported by sources."

        # Log this turn: retrieved chunks + generated response
        turn_num = len(state.turns) + 1
        state.log.info("── TURN %d: %s ──", turn_num, speaker)
        for i, s in enumerate(snippets):
            state.log.info("  chunk[%d] (%s):\n%s", i + 1, s["source"], s["text"])
        state.log.info("  RESPONSE: %s", response)

        if state.queue:
            loop.call_soon_threadsafe(state.queue.put_nowait, "[END_TURN]")

        return response
