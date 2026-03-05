# plan.md

## Goal
Build a minimal working demo with two independent debating agents (Caesar, Pompey), each using its own RAG corpus, exposed via an OpenAI-compatible FastAPI endpoint for Open WebUI.

## Options considered
- Option A: Open WebUI + OpenAI-compatible FastAPI endpoint
- Option B: Gradio fallback

Chosen: Option B — Gradio (ready-made, stable, separate bubbles per turn).

## Implementation checklist
- [x] Scaffold repo structure
- [x] Add minimal dependencies and Docker setup
- [x] Implement RAG with ChromaDB + OpenAI embeddings
- [x] Split corpora into caesar/pompey collections
- [x] Implement separate agent histories keyed by conversation_id
- [x] Implement debate worker with stop conditions
- [x] Implement `/v1/chat/completions` command handling
- [x] Add streaming chunk support (SSE)
- [x] Add legal sample sources + public-domain fetch script
- [x] Document full run flow in README
- [x] Compile-check Python files

## Improvements completed
- [x] RAG retrieval: structured query (topic + opponent's last point), XML snippet tags, distance-based filtering (`RAG_MAX_DISTANCE`), overfetch k×2 + dedup
- [x] Snippet injection: XML `<snippet id="1" source="...">text</snippet>` before conversation history
- [x] Sources citation format: grouped by file (`Sources: filename.txt [1][3], other.txt [2].`)
- [x] Longer debates: `max_turns` increased to 30, conversation history capped to last 40 turns
- [x] Removed `max_seconds` time limit — debates run until `max_turns` or manual stop
- [x] Removed MODERATOR AGENDA UPDATE from Gradio UI
- [x] Chroma skip-if-indexed: avoids delete/recreate on every startup (delete `chroma/` dir to force re-index)
- [x] Bug fixes: `min_chunk_chars` check, Chroma metadata type casts, Gradio theme forward reference

## Explicit simplifications
- No AutoGen: direct turn loop is smaller and easier to maintain.
- Streaming is OpenAI-like SSE chunks (good enough for live feel).
- Basic text chunking for RAG to keep implementation small.
