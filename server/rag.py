from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.api.types import EmbeddingFunction, Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI

# -- Embedding wrapper (works with any OpenAI-compatible endpoint) ----------

class _OpenAICompatibleEmbedding(EmbeddingFunction):  # type: ignore[type-arg]
    """Calls ``/v1/embeddings`` on any compatible server."""

    def __init__(self, api_key: str = "not-needed", model_name: str = "default",
                 api_base: str | None = None):
        kw: dict[str, Any] = {"api_key": api_key or "not-needed"}
        if api_base:
            kw["base_url"] = api_base
        self._client = OpenAI(**kw)
        self._model = model_name

    def __call__(self, input: Any) -> Embeddings:
        resp = self._client.embeddings.create(model=self._model, input=input)
        return cast(Embeddings, [item.embedding for item in resp.data])


# -- Text splitter ----------------------------------------------------------
# Historical plain-text sources (Gutenberg translations of Caesar, Plutarch,
# Cicero, etc.) have long paragraphs (median 300-1800 chars), heavy use of
# abbreviations (B.C., Cn., M., C.) and formal sentence structure.
#
# Key choices:
# - chunk_size 1500: keeps full arguments/paragraphs intact (avg para ~900
#   chars, median ~1200); ~270 tokens — well within any embedding model limit.
#   Mid-sentence break rate 19.4% vs 25.8% at 1200 and 60% with bare ".".
# - Separators use ". " (dot-space) not bare "." to avoid splitting on Roman
#   abbreviations like "B.C.", "Cn. Pompeius", "M. Crassus".
# - ", " and " " as low-priority fallbacks ensure graceful degradation.
# - chunk_overlap 300: generous context continuity between adjacent chunks,
#   important for narrative texts where events span paragraphs.

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=300,
    separators=["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " "],
    strip_whitespace=True,
)

Snippet = dict[str, str]  # {"text": ..., "source": ...}

# Strip stray citation / footnote markers that would confuse the LLM.
# Matches patterns like [56], (43), [p. 12], [p.204], [pg 5], [vol. ii], etc.
_CITATION_RE = re.compile(
    r"\s*"              # optional leading whitespace
    r"(?:"
    r"\[\d+\]"          # [56]
    r"|\(\d+\)"         # (43)
    r"|\[p\.?\s*\d+\]"  # [p. 12] / [p12]
    r"|\[pg\.?\s*\d+\]" # [pg 5]
    r"|\[vol\.?\s*\w+\]"# [vol. ii]
    r")"
)

def _clean_chunk(text: str) -> str:
    """Remove citation/footnote markers from a chunk."""
    return _CITATION_RE.sub("", text).strip()


# -- RAG --------------------------------------------------------------------

class RAG:
    def __init__(self, persist_dir: str, embedding_model: str,
                 embedding_api_key: str, embedding_base_url: str | None = None):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self._ef = _OpenAICompatibleEmbedding(
            api_key=embedding_api_key, model_name=embedding_model,
            api_base=embedding_base_url,
        )
        self.min_chunk_chars = int(os.getenv("RAG_MIN_CHUNK_CHARS", "120"))
        self.max_per_source = int(os.getenv("RAG_MAX_SNIPPETS_PER_SOURCE", "4"))

    def _col(self, name: str):
        return self.client.get_or_create_collection(name=name, embedding_function=self._ef)

    # -- Indexing ------------------------------------------------------------

    def build_or_load_index(
        self, collection_name: str, docs_path: str,
        exclude_filenames: Iterable[str] | None = None,
    ) -> None:
        """Build a Chroma collection from ``*.txt`` files in *docs_path*.

        Skips if the collection already has data (delete ``chroma/`` dir to
        force a full re-index).
        """
        col = self._col(collection_name)
        if col.count() > 0:
            print(f"[RAG] {collection_name}: {col.count()} chunks already indexed, skipping")
            return
        docs_dir = Path(docs_path)
        docs_dir.mkdir(parents=True, exist_ok=True)

        excluded = set(exclude_filenames or [])
        ids: list[str] = []
        texts: list[str] = []
        metas: list[dict[str, str]] = []

        for f in sorted(docs_dir.glob("*.txt")):
            if f.name in excluded:
                continue
            chunks = _splitter.split_text(f.read_text(encoding="utf-8", errors="ignore"))
            for i, chunk in enumerate(chunks):
                cleaned = _clean_chunk(chunk)
                if len(cleaned) < self.min_chunk_chars:
                    continue
                ids.append(f"{f.name}:{i}")
                texts.append(cleaned)
                metas.append({"source": f.name})

        if ids:
            # Batch to stay within embedding API token limits
            batch = int(os.getenv("RAG_EMBED_BATCH_SIZE", "100"))
            for i in range(0, len(ids), batch):
                s = slice(i, i + batch)
                col.add(ids=ids[s], documents=texts[s], metadatas=metas[s])  # type: ignore[arg-type]

        print(f"[RAG] {collection_name}: {len(ids)} chunks indexed")

    # -- Retrieval -----------------------------------------------------------

    def retrieve(
        self,
        collection_name: str,
        query: str,
        k: int = 4,
        max_distance: float = float(os.getenv("RAG_MAX_DISTANCE", "1.45")),
    ) -> list[Snippet]:
        col = self._col(collection_name)

        raw = col.query(
            query_texts=[query],
            n_results=k * 2,
            include=["documents", "metadatas", "distances"],
        )
        docs = (raw.get("documents") or [[]])[0]  # type: ignore[index]
        meta = (raw.get("metadatas") or [[]])[0]  # type: ignore[index]
        dists = (raw.get("distances") or [[]])[0]  # type: ignore[index]

        snippets: list[Snippet] = []
        seen_text: set[str] = set()
        src_count: dict[str, int] = {}

        for d, m, dist in zip(docs, meta, dists):
            if dist > max_distance:
                continue
            src = str((m or {}).get("source", "unknown"))  # type: ignore[union-attr]
            norm = " ".join(str(d).split())
            if not norm or norm in seen_text:
                continue
            seen_text.add(norm)
            if src_count.get(src, 0) >= self.max_per_source:
                continue
            src_count[src] = src_count.get(src, 0) + 1
            snippets.append({"text": str(d), "source": src})

        return snippets[:k]
