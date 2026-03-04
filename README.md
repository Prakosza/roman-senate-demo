# roman-senate-demo

Minimal demo: two independent agents (**Caesar** and **Pompey**) debate turn-by-turn with separate RAG sources and separate agent memory.

## Design choices (low-LOC, existing tools)

- **No custom frontend code** for production path.
- **UI:** Gradio (ready-made, stable) for one-turn-per-bubble behavior.
- **Optional UI:** Open WebUI (also ready-made), but via OpenAI-compatible API it shows one streaming assistant bubble per request.
- **Backend:** small FastAPI OpenAI-compatible endpoint.

## What it supports

- `/debate start <topic>`
- `/debate stop`
- auto-stop by `MAX_SECONDS` and `MAX_TURNS`
- strict agent isolation:
  - Caesar history separate from Pompey history
  - Caesar retrieves only from `caesar_collection`
  - Pompey retrieves only from `pompey_collection`

## Model provider flexibility (external + local)

Both chat and embeddings are OpenAI-compatible and configurable independently:

- Chat: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- Embeddings: `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`

This works with OpenAI and local backends (vLLM/Ollama/NIM/LM Studio) if they expose compatible endpoints.

## Repo layout

```text
roman-senate-demo/
  server/
    main.py
    debate.py
    rag.py
    prompts.py
  data/
    caesar_docs/
    pompey_docs/
  scripts/
    fetch_public_domain_sources.py
  gradio_app.py
  Dockerfile
  docker-compose.yml
  requirements.txt
```

## Legal sources policy

No copyrighted books are committed.

Included:
- authored placeholders (`sample_*.txt`)
- public-domain English texts:
  - `data/caesar_docs/caesar_commentaries_pg10657_selected.txt`
  - `data/caesar_docs/appian_civil_wars_pg28334_selected.txt`
  - `data/pompey_docs/plutarch_lives_vol3_pg14140_selected.txt`
  - `data/pompey_docs/appian_civil_wars_pg28334_selected.txt`

Optional fetch script:

```bash
python3 scripts/fetch_public_domain_sources.py
```

## Run

```bash
cp .env.example .env
# set keys/models/base URLs as needed

docker-compose up --build
```

### UIs

- **Gradio (recommended for separate bubbles):** `http://localhost:7860`
- **Open WebUI (optional):** `http://localhost:3000`
- **Backend API:** `http://localhost:8000/v1/chat/completions`

## Quick demo

1. Open Gradio (`:7860`)
2. Topic: `Rubicon legality`
3. Click **Start debate**
4. Verify separate Caesar/Pompey bubbles
5. Send agenda update
6. Click **Stop debate**

## API demo

```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dummy' \
  -H 'X-Chat-Id: test-1' \
  -d '{"model":"roman-senate","stream":true,"messages":[{"role":"user","content":"/debate start Rubicon legality"}]}'
```

## Notes

- AutoGen intentionally omitted to keep code smaller and easier to run/debug.
- RAG is intentionally simple (text files + chunking + Chroma).
