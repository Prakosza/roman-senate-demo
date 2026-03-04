# roman-senate-demo

Minimal demo: two independent agents (**Caesar** and **Pompey**) debate in one chat, each grounded only in its own RAG corpus.

## Think-and-challenge checkpoint

- **Option A (chosen):** Open WebUI + OpenAI-compatible FastAPI backend.
- **Option B (fallback):** Gradio UI + direct backend call.

Why A is simplest for this goal: Open WebUI gives a ready-made, pretty chat UI with almost no frontend code. We only implement one backend endpoint (`/v1/chat/completions`) and commands.

## What is implemented

- OpenAI-compatible backend (`POST /v1/chat/completions`)
- Commands:
  - `/debate start <topic>`
  - `/debate stop`
- Auto-stop:
  - `MAX_SECONDS`
  - `MAX_TURNS`
- Two independent agents:
  - separate histories (`history_caesar`, `history_pompey`)
  - separate RAG collections (`caesar_collection`, `pompey_collection`)
  - separate source folders (`data/caesar_docs`, `data/pompey_docs`)
- Streaming support (SSE chunks) for live-feeling output when `stream=true`

## Architecture

```text
Open WebUI -> /v1/chat/completions (FastAPI)
                       |
                       +-> DebateManager (turn loop)
                       |      - Caesar history
                       |      - Pompey history
                       |
                       +-> RAG (ChromaDB + OpenAI embeddings)
                              - caesar_collection <- data/caesar_docs
                              - pompey_collection <- data/pompey_docs
```

## Repo layout

```text
roman-senate-demo/
  server/
    __init__.py
    main.py
    debate.py
    rag.py
    prompts.py
  data/
    caesar_docs/
    pompey_docs/
  scripts/
    fetch_public_domain_sources.py
  Dockerfile
  docker-compose.yml
  requirements.txt
  README.md
```

## Legal sources policy

No copyrighted books are committed.

This repo includes:
- small authored sample `.txt` snippets (safe placeholders)
- optional downloader for public-domain sources:
  - `scripts/fetch_public_domain_sources.py`

You can also add your own files into:
- `data/caesar_docs`
- `data/pompey_docs`

## Run

1. Prepare env:

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY
```

2. (Optional) Fetch public-domain sources:

```bash
python3 scripts/fetch_public_domain_sources.py
```

3. Start stack:

```bash
docker compose up --build
```

4. Open WebUI:
- URL: `http://localhost:3000`
- Add OpenAI-compatible connection in Open WebUI settings:
  - Base URL: `http://senate-server:8000/v1` (inside Docker network), or `http://localhost:8000/v1` depending on setup
  - API key: any non-empty dummy value (backend accepts it)
  - Model: `roman-senate`

## Demo script

In chat:

```text
/debate start Rubicon legality
```

Then (optional moderator interventions):

```text
Focus on constitutional procedure only.
Now address public safety vs legality.
```

Stop manually:

```text
/debate stop
```

## Behavior notes

- During active debate, non-command user messages are treated as agenda updates.
- Each turn is labeled `Caesar` or `Pompey`.
- Prompt rule enforces groundedness: if support is missing, model should say `Not supported by sources.`
- Sources are printed at end of each turn.

## Acceptance checks

1. Start containers, open WebUI, select endpoint/model.
2. Put texts into both data folders.
3. Run `/debate start Rubicon legality`.
4. See alternating Caesar/Pompey messages.
5. Send `/debate stop`; debate halts quickly.
6. Auto-stop works after `MAX_SECONDS`.
7. Caesar uses only Caesar collection, Pompey only Pompey collection.
8. Code remains small and readable.

## Simplifications (intentional)

- No AutoGen dependency (direct turn loop is smaller and clearer).
- RAG chunking is intentionally simple fixed-size chunking.
- Streaming is chunked SSE in OpenAI-like format; not a perfect full OpenAI clone.
