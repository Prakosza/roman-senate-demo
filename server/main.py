from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse, StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from .debate import DebateManager
from .rag import RAG

load_dotenv()

# LLM provider (OpenAI-compatible: OpenAI, vLLM, Ollama, NIM, etc.)
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")  # optional

# Embedding provider (also OpenAI-compatible)
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or LLM_API_KEY
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL") or os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL") or LLM_BASE_URL

MAX_SECONDS = int(os.getenv("MAX_SECONDS", "180"))
MAX_TURNS = int(os.getenv("MAX_TURNS", "12"))
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma")

if not LLM_API_KEY:
    raise RuntimeError("Set LLM_API_KEY (or OPENAI_API_KEY)")
if not EMBEDDING_API_KEY:
    raise RuntimeError("Set EMBEDDING_API_KEY (or LLM_API_KEY / OPENAI_API_KEY)")

llm_kwargs = {"api_key": LLM_API_KEY}
if LLM_BASE_URL:
    llm_kwargs["base_url"] = LLM_BASE_URL
openai_client = OpenAI(**llm_kwargs)

rag = RAG(
    persist_dir=CHROMA_DIR,
    embedding_model=EMBEDDING_MODEL,
    embedding_api_key=EMBEDDING_API_KEY,
    embedding_base_url=EMBEDDING_BASE_URL,
)
rag.build_or_load_index("caesar_collection", "./data/caesar_docs")
rag.build_or_load_index("pompey_collection", "./data/pompey_docs")

manager = DebateManager(
    rag=rag,
    openai_client=openai_client,
    model=LLM_MODEL,
    max_seconds=MAX_SECONDS,
    max_turns=MAX_TURNS,
)

app = FastAPI(title="Roman Senate Demo", version="0.2.0")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="roman-senate")
    messages: List[ChatMessage]
    stream: bool = False
    user: Optional[str] = None


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "llm_model": LLM_MODEL, "embedding_model": EMBEDDING_MODEL}


@app.get("/v1/models")
async def models() -> Dict[str, Any]:
    return {
        "object": "list",
        "data": [{"id": "roman-senate", "object": "model", "owned_by": "roman-senate-demo"}],
    }


def _conversation_id(req: ChatCompletionRequest, x_chat_id: Optional[str]) -> str:
    return x_chat_id or req.user or "default"


def _latest_user_message(messages: List[ChatMessage]) -> str:
    for m in reversed(messages):
        if m.role == "user":
            return m.content.strip()
    return ""


def _chat_response_text(text: str) -> Dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "roman-senate",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
    }


def _sse_chunk(content: str, finish_reason: Optional[str] = None) -> str:
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "roman-senate",
        "choices": [{"index": 0, "delta": {"content": content} if content else {}, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


async def _stream_state(conversation_id: str):
    state = manager.get_state(conversation_id)
    if not state or not state.queue:
        yield _sse_chunk("No active debate.", "stop")
        yield "data: [DONE]\n\n"
        return

    yield _sse_chunk("Debate started. Type /debate stop to end.\n\n")
    while True:
        item = await state.queue.get()
        if item == "[DEBATE_DONE]":
            yield _sse_chunk("\nDebate finished.", "stop")
            yield "data: [DONE]\n\n"
            break
        yield _sse_chunk(item + "\n\n")


@app.post("/v1/chat/completions")
async def chat_completions(
    req: ChatCompletionRequest,
    authorization: Optional[str] = Header(default=None),
    x_chat_id: Optional[str] = Header(default=None, alias="X-Chat-Id"),
):
    _ = authorization  # accept any non-empty key

    convo_id = _conversation_id(req, x_chat_id)
    latest = _latest_user_message(req.messages)

    if latest.lower().startswith("/debate start"):
        topic = latest[len("/debate start") :].strip() or "Was Caesar justified?"
        await manager.start_debate(convo_id, topic)
        if req.stream:
            return StreamingResponse(_stream_state(convo_id), media_type="text/event-stream")
        return JSONResponse(_chat_response_text("Debate started. Type /debate stop to end."))

    if latest.lower().startswith("/debate stop"):
        stopped = manager.stop_debate(convo_id)
        return JSONResponse(_chat_response_text("Debate stopped." if stopped else "No active debate."))

    if manager.is_active(convo_id):
        manager.update_agenda(convo_id, latest)
        return JSONResponse(_chat_response_text("Agenda updated."))

    return JSONResponse(_chat_response_text("No active debate. Use /debate start <topic>."))
