# Roman Senate

Two LLM agents, Caesar and Pompey, debate a topic you give them. Each one has its own conversation memory and its own retrieval index built from ancient sources, and backs factual claims with numbered citations to those sources.

Pick a topic like "Rubicon legality" or "Should Rome build more aqueducts?" and they argue it turn by turn in the browser.

## How it works

```mermaid
flowchart LR
    UI["Gradio UI"] -- "/debate start topic" --> API["FastAPI<br/>/v1/chat/completions"]
    API -- "SSE token stream" --> UI
    API --> DM["DebateManager"]
    DM -- "Caesar's turns" --> RC[("caesar_collection<br/>Chroma")]
    DM -- "Pompey's turns" --> RP[("pompey_collection<br/>Chroma")]
    DM --> LLM["Any OpenAI-compatible LLM"]
```

Each turn goes like this:

1. **Query.** The search query is the topic plus the first ~200 characters of the opponent's last turn. Embedding a whole speech dilutes the query.
2. **Retrieval** from the speaker's own collection only. It fetches 2×k candidates, drops chunks past a distance cutoff, drops duplicates and caps how many chunks can come from one file, so a single long book can't fill the whole context.
3. **Prompt.** The request is built from the speaker's point of view: his own past turns are `assistant` messages, the opponent's are `user` messages. Retrieved chunks go into the last user message as numbered `<document>` blocks, so the system prompt (character, debate rules) stays the same on every turn.
4. **Streaming.** Tokens are streamed back over SSE. The backend mixes in a few control markers (`[START:Caesar]`, `[END_TURN]`, `[DEBATE_DONE]`) so the UI knows where one speech ends and the next begins.

The prompts ask for `[n]` citations on concrete factual claims and for "Not supported by sources." when nothing backs a claim. Every turn is written to `logs/debate.log` together with the chunks the model was given, which makes it easy to check whether a citation actually matches its source.

A few other decisions worth mentioning:

- **The backend is itself OpenAI-compatible.** Anything that speaks the chat completions API can start a debate, not just the bundled UI.
- **The model provider is just configuration.** Chat and embeddings can come from OpenAI, vLLM, Ollama, LM Studio, NVIDIA NIM or llama.cpp, and from two different servers if needed.
- **Chunking is tuned to the texts.** The sources are old translations with long paragraphs and abbreviations like "B.C.", so chunks are 1500 characters with 300 overlap and split on `. ` rather than `.`. Footnote markers such as `[56]` or `[p. 12]` are stripped, because otherwise the model reads them as citations. The reasoning is in [server/rag.py](server/rag.py).

## Running it

You need an OpenAI API key, or any OpenAI-compatible server for chat and embeddings.

```bash
cp .env.example .env
# set LLM_API_KEY, LLM_MODEL (e.g. gpt-5-mini) and EMBEDDING_MODEL (e.g. text-embedding-3-large)
docker compose up --build
```

Then open http://localhost:7860.

On the first start the backend splits and embeds everything in `data/` into `chroma/`. That takes a few minutes and uses the embedding API. Later starts reuse the index; delete `chroma/` to rebuild it.

Without Docker:

```bash
./run.sh start    # creates .venv on first run, starts backend :8000 and UI :7860
./run.sh fresh    # same, but rebuilds the Chroma index
./run.sh logs
./run.sh stop
```

### Local models

Point the base URLs at your server and leave the keys empty:

```bash
LLM_BASE_URL=http://localhost:11434/v1          # Ollama, vLLM, LM Studio, NIM...
LLM_MODEL=llama3.1:8b
EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_MODEL=nomic-embed-text
```

For an NVIDIA DGX Spark there is a compose overlay that runs gpt-oss-120b and Qwen3-Embedding-4B through llama.cpp. Download instructions are at the top of the file:

```bash
docker compose -f docker-compose.yml -f docker-compose-spark.yml up -d --build
```

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `LLM_MODEL` | (required) | Chat model name |
| `LLM_API_KEY` | | Empty is fine for local servers |
| `LLM_BASE_URL` | OpenAI | Any OpenAI-compatible `/v1` endpoint |
| `LLM_TEMPERATURE` | not sent | Reasoning models reject a temperature |
| `EMBEDDING_MODEL` | (required) | Embedding model name |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` | same as LLM | Embeddings can come from a different server |
| `MAX_TURNS` | 30 | The debate stops after this many speeches |
| `RAG_RETRIEVAL_K` | 14 | Chunks per turn |
| `RAG_MAX_SNIPPETS_PER_SOURCE` | 4 | Cap per source file per turn |
| `RAG_MAX_DISTANCE` | 1.45 | Chunks further than this are dropped |
| `RAG_MIN_CHUNK_CHARS` | 120 | Shorter chunks aren't indexed |
| `RAG_EMBED_BATCH_SIZE` | 100 | Chunks per embedding request while indexing |
| `CHROMA_DIR` / `DEBATE_LOG_DIR` | `./chroma` / `./logs` | |

## API

```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'X-Chat-Id: demo-1' \
  -d '{"model": "roman-senate", "stream": true,
       "messages": [{"role": "user", "content": "/debate start Rubicon legality"}]}'
```

Send `/debate stop` with the same `X-Chat-Id` to end it early. `GET /health` returns the configured models.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests cover retrieval filtering, how each turn's messages are built and the stream of tokens and control markers the UI relies on. The LLM and the vector store are replaced with fakes, so no API key is needed. GitHub Actions runs them, plus ruff, on every pull request and push to master.

## Project layout

```text
server/
  main.py       FastAPI app, config, startup indexing
  debate.py     debate loop, prompt assembly, streaming
  rag.py        chunking, indexing and filtered retrieval (Chroma)
  prompts.py    Caesar and Pompey system prompts
gradio_app.py   web UI
data/           source texts, one folder per senator
scripts/        downloads and cleans the source texts
tests/
```

## Sources

All texts are public domain English translations from Project Gutenberg: Caesar's *Commentaries*, Suetonius, Plutarch, Lucan's *Pharsalia* and Cicero's letters to Atticus. [RAG_SOURCES.md](RAG_SOURCES.md) lists every file and why it's there, and `scripts/fetch_public_domain_sources.py` downloads and cleans them again.

## Limitations

- Citation accuracy isn't measured automatically yet. Checking it means reading `logs/debate.log`.
- Lucan's *Pharsalia* is in both corpora under different file names, so on that text the two senators share sources.
- When a turn starts, the opponent's last speech and the retrieved sources arrive as two `user` messages in a row. OpenAI-style APIs accept that, but some local chat templates insist on strict user/assistant alternation and reject it.
- Debates live in memory, so restarting the backend ends them.
