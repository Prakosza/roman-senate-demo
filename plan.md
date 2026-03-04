# plan.md

## Goal
Build a minimal working demo with two independent debating agents (Caesar, Pompey), each using its own RAG corpus, exposed via an OpenAI-compatible FastAPI endpoint for Open WebUI.

## Options considered
- Option A: Open WebUI + OpenAI-compatible FastAPI endpoint
- Option B: Gradio fallback

Chosen: Option A (prettier UI with near-zero frontend effort).

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

## Explicit simplifications
- No AutoGen: direct turn loop is smaller and easier to maintain.
- Streaming is OpenAI-like SSE chunks (good enough for live feel).
- Basic text chunking for RAG to keep implementation small.
