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


class _OpenAICompatibleEmbedding(EmbeddingFunction):  # type: ignore[type-arg]
    """Chroma embedding function that calls /v1/embeddings on any OpenAI-compatible server."""

    def __init__(self, api_key: str = "not-needed", model_name: str = "default", api_base: str | None = None):
        kw: dict[str, Any] = {"api_key": api_key or "not-needed"}
        if api_base:
            kw["base_url"] = api_base
        self._client = OpenAI(**kw)
        self._model = model_name

    def __call__(self, input: Any) -> Embeddings:
        resp = self._client.embeddings.create(model=self._model, input=input)
        return cast(Embeddings, [item.embedding for item in resp.data])


# The sources are Gutenberg translations (Caesar, Plutarch, Cicero...) with long
# paragraphs (median ~1200 chars) and lots of abbreviations like "B.C.", "Cn." or "M.".
#
# - chunk_size 1500 keeps most paragraphs whole (~270 tokens, fine for any embedding
#   model). Mid-sentence breaks: 19.4% at 1500 vs 25.8% at 1200 and ~60% when
#   splitting on a bare ".".
# - ". " instead of "." so dotted abbreviations like "B.C." aren't cut in the middle.
#   Sentence-level separators only kick in for paragraphs longer than chunk_size.
# - 300 chars of overlap because events in narrative text often span paragraphs.
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=300,
    separators=["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " "],
    strip_whitespace=True,
)

Snippet = dict[str, str]  # {"text": ..., "source": ...}

# Footnote and page markers left over from the Gutenberg texts: [56], (43), [p. 12],
# [pg 5], [vol. ii]. They look like citations, which confuses the model.
_CITATION_RE = re.compile(
    r"\s*"
    r"(?:"
    r"\[\d+\]"
    r"|\(\d+\)"
    r"|\[p\.?\s*\d+\]"
    r"|\[pg\.?\s*\d+\]"
    r"|\[vol\.?\s*\w+\]"
    r")"
)


def _clean_chunk(text: str) -> str:
    return _CITATION_RE.sub("", text).strip()


class RAG:
    def __init__(
        self,
        persist_dir: str,
        embedding_model: str,
        embedding_api_key: str,
        embedding_base_url: str | None = None,
    ):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self._ef = _OpenAICompatibleEmbedding(
            api_key=embedding_api_key,
            model_name=embedding_model,
            api_base=embedding_base_url,
        )
        self.min_chunk_chars = int(os.getenv("RAG_MIN_CHUNK_CHARS", "120"))
        self.max_per_source = int(os.getenv("RAG_MAX_SNIPPETS_PER_SOURCE", "4"))
        self.max_distance = float(os.getenv("RAG_MAX_DISTANCE", "1.45"))
        self.embed_batch_size = int(os.getenv("RAG_EMBED_BATCH_SIZE", "100"))

    def _col(self, name: str):
        return self.client.get_or_create_collection(name=name, embedding_function=self._ef)

    def build_or_load_index(
        self,
        collection_name: str,
        docs_path: str,
        exclude_filenames: Iterable[str] | None = None,
    ) -> None:
        """Index every *.txt file in docs_path into a Chroma collection.

        Does nothing if the collection already has data. Delete the chroma/
        directory to force a re-index.
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

        # Batched so a single request doesn't hit the embedding API's token limit.
        for i in range(0, len(ids), self.embed_batch_size):
            s = slice(i, i + self.embed_batch_size)
            col.add(ids=ids[s], documents=texts[s], metadatas=metas[s])  # type: ignore[arg-type]

        print(f"[RAG] {collection_name}: {len(ids)} chunks indexed")

    def retrieve(
        self,
        collection_name: str,
        query: str,
        k: int = 4,
        max_distance: float | None = None,
    ) -> list[Snippet]:
        """Return up to k relevant, non-duplicated snippets.

        Fetches 2*k candidates, then drops anything past the distance cutoff,
        exact duplicates, and anything over the per-source cap, so one long book
        can't fill the whole context.
        """
        if max_distance is None:
            max_distance = self.max_distance
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

        for d, m, dist in zip(docs, meta, dists, strict=False):
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
