# roman-senate-demo

Minimal demo: two independent agents (**Caesar** and **Pompey**) debate turn-by-turn with separate RAG sources and separate agent memory.
RAG is used for grounding factual claims, while tone and argument style stay in-character (Roman statesmen, not modern historians).

## Design choices (low-LOC, existing tools)

- **No custom frontend code** for production path.
- **UI:** Gradio (ready-made, stable) for one-turn-per-bubble behavior.
- **Optional UI:** Open WebUI (also ready-made), but via OpenAI-compatible API it shows one streaming assistant bubble per request.
- **Backend:** small FastAPI OpenAI-compatible endpoint.

## What it supports

- `/debate start <topic>`
- `/debate stop`
- auto-stop by `MAX_TURNS` (default 30)
- strict agent isolation:
  - Caesar history separate from Pompey history
  - Caesar retrieves only from `caesar_collection`
  - Pompey retrieves only from `pompey_collection`
  - duplicate filenames across corpora are excluded to keep sources perspective-specific
- distinct in-character rhetoric:
  - Caesar: first-person defensive command voice, aggressive rebuttal
  - Pompey: first-person legal prosecution voice, aggressive attack
- role-driven debate behavior:
  - opening sentence must rebut the opponent's latest claim
  - agents address each other directly as political rivals
  - neutral academic phrasing is discouraged
- structured retrieval queries (topic + opponent's last point for rebuttal context)
- retrieval diversity guardrails:
  - over-fetch k×2 candidates + deduplicate before final selection
  - distance-based filtering (`RAG_MAX_DISTANCE`, default 1.45) to drop low-relevance chunks
  - cap repeated snippets from one source per turn (`RAG_MAX_SNIPPETS_PER_SOURCE`)
- XML-tagged snippet injection (`<snippet id="1" source="...">...</snippet>`)
- conversation history capped to last 40 turns to limit context length
- response grounding:
  - citations use snippet ids inline (e.g. `[1]`, `[2][5]`)
  - Sources line groups cited ids by file: `Sources: filename.txt [1][3], other.txt [2].`
  - rhetorical/strategic statements can be uncited
  - unsupported concrete claims should be stated as `Not supported by sources.`

## Model provider flexibility (external + local)

Both chat and embeddings use the **OpenAI-compatible** API format, so any
server that exposes `/v1/chat/completions` and `/v1/embeddings` works — no
code changes needed.

| Variable | Purpose | Example (OpenAI) | Example (local NIM) |
|---|---|---|---|
| `LLM_API_KEY` | Chat API key (optional for local) | `sk-…` | *(leave empty)* |
| `LLM_BASE_URL` | Chat endpoint | *(omit = openai.com)* | `http://localhost:8000/v1` |
| `LLM_MODEL` | **Required** — model name | `gpt-5-mini` | `meta/llama-3.1-8b-instruct` |
| `EMBEDDING_API_KEY` | Embed API key (falls back to `LLM_API_KEY`) | `sk-…` | *(leave empty)* |
| `EMBEDDING_BASE_URL` | Embed endpoint (falls back to `LLM_BASE_URL`) | *(omit)* | `http://localhost:9000/v1` |
| `EMBEDDING_MODEL` | **Required** — embedding model name | `text-embedding-3-large` | `nvidia/nv-embedqa-e5-v5` |

**No API key is required for local models** — the placeholder `"not-needed"` is
used automatically when the key is empty or unset.

### Quick-start: NVIDIA DGX / local models

```bash
# 1. Serve models (example: NIM containers on DGX Spark)
#    Chat:      localhost:8000
#    Embeddings: localhost:9000

# 2. Configure .env
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=meta/llama-3.1-8b-instruct
EMBEDDING_BASE_URL=http://localhost:9000/v1
EMBEDDING_MODEL=nvidia/nv-embedqa-e5-v5

# 3. Run
docker-compose up --build   # or: ./run.sh
```

Also works with **vLLM**, **Ollama** (`http://localhost:11434/v1`), **LM Studio**, **text-embeddings-inference**, etc.

Optional RAG tuning env vars:
- `RAG_RETRIEVAL_K` (snippets per turn, default `14`)
- `RAG_MAX_SNIPPETS_PER_SOURCE` (cap per source in one turn, default `4`)
- `RAG_MIN_CHUNK_CHARS` (skip tiny chunks, default `120`)
- `RAG_MAX_DISTANCE` (L² distance cutoff for relevance filtering, default `1.45`)
- `RAG_EMBED_BATCH_SIZE` (chunks per embedding API call during indexing, default `100`)

## Prompt contract (short)

- Speak in first person as Caesar/Pompey.
- First sentence: direct rebuttal to the previous turn.
- Snippets are injected as XML: `<snippet id="1" source="filename.txt">text</snippet>`.
- Cite snippet ids inline for concrete factual/legal claims (e.g. `[1]`, `[2][5]`).
- If a concrete claim lacks support: `Not supported by sources.`
- End with a grouped sources line: `Sources: filename.txt [1][3], other.txt [2].`

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
  - Caesar corpus:
    - `data/caesar_docs/caesar_commentaries_pg10657_full.txt`
    - `data/caesar_docs/suetonius_twelve_caesars_pg6400.txt`
    - `data/caesar_docs/lucan_pharsalia_pg602_caesar_context.txt`
    - `data/caesar_docs/plutarch_lives_pg674_caesar_context.txt`
  - Pompey corpus:
    - `data/pompey_docs/plutarch_lives_vol3_pg14140_full.txt`
    - `data/pompey_docs/plutarch_lives_vol2_pg14114_pompey_context.txt`
    - `data/pompey_docs/lucan_pharsalia_pg602_pompey_context.txt`
    - `data/pompey_docs/plutarch_lives_pg674_pompey_context.txt`
    - `data/pompey_docs/caesar_commentaries_pg10657_civil_war_context.txt`
    - `data/pompey_docs/cicero_letters_to_atticus_vol1_pg58418.txt`
    - `data/pompey_docs/cicero_letters_to_atticus_vol2_pg50692.txt`
    - `data/pompey_docs/cicero_letters_to_atticus_vol3_pg51403.txt`

Optional fetch script:

```bash
python3 scripts/fetch_public_domain_sources.py
```

The fetch script removes legacy noisy/duplicate files (`appian_civil_wars_pg28334_selected.txt`,
`caesar_commentaries_pg10657_selected.txt`, `plutarch_lives_vol3_pg14140_selected.txt`) and performs
basic deduplication in each corpus to reduce repeated material.

Full per-source documentation is in `RAG_SOURCES.md`.

## Run

```bash
cp .env.example .env
# set keys/models/base URLs as needed

docker-compose up --build
```

Note: on first startup Chroma collections are built from the text files in `data/`.
Delete the `chroma/` directory to force a full re-index after corpus or embedding model changes.

### UIs

- **Gradio (recommended for separate bubbles):** `http://localhost:7860`
- **Open WebUI (optional):** `http://localhost:3000`
- **Backend API:** `http://localhost:8000/v1/chat/completions`

## Quick demo

1. Open Gradio (`:7860`)
2. Topic: `Rubicon legality`
3. Click **Start debate**
4. Verify separate Caesar/Pompey bubbles
5. Verify turns include inline snippet citations (e.g. `[1]`) and a grouped `Sources:` line
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
- RAG is intentionally simple (text files + recursive text splitting + Chroma).
- Chroma collections are rebuilt on startup to avoid stale indexes after model or corpus changes.
