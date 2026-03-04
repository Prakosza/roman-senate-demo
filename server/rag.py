from __future__ import annotations

from pathlib import Path
from typing import List, Dict

import chromadb
from openai import OpenAI


def _chunk_text(text: str, chunk_size: int = 900) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks: List[str] = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + chunk_size])
        i += chunk_size
    return chunks


class OpenAICompatibleEmbeddingFunction:
    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def __call__(self, input: List[str]) -> List[List[float]]:
        resp = self.client.embeddings.create(model=self.model, input=input)
        return [d.embedding for d in resp.data]


class RAG:
    def __init__(
        self,
        persist_dir: str,
        embedding_model: str,
        embedding_api_key: str,
        embedding_base_url: str | None = None,
    ):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.embedding_function = OpenAICompatibleEmbeddingFunction(
            model=embedding_model,
            api_key=embedding_api_key,
            base_url=embedding_base_url,
        )

    def build_or_load_index(self, collection_name: str, docs_path: str) -> None:
        collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
        )

        docs_dir = Path(docs_path)
        if not docs_dir.exists():
            docs_dir.mkdir(parents=True, exist_ok=True)

        existing = set(collection.get(include=[]).get("ids", []))
        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, str]] = []

        for file in sorted(docs_dir.glob("*.txt")):
            content = file.read_text(encoding="utf-8", errors="ignore")
            for idx, chunk in enumerate(_chunk_text(content)):
                doc_id = f"{file.name}:{idx}"
                if doc_id in existing:
                    continue
                ids.append(doc_id)
                documents.append(chunk)
                metadatas.append({"source": file.name})

        if ids:
            collection.add(ids=ids, documents=documents, metadatas=metadatas)

    def retrieve(self, collection_name: str, query: str, k: int = 4) -> List[Dict[str, str]]:
        collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
        )
        result = collection.query(query_texts=[query], n_results=max(k, 8))
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]

        snippets: List[Dict[str, str]] = []
        for doc, meta in zip(docs, metas):
            snippets.append({
                "text": doc,
                "source": (meta or {}).get("source", "unknown"),
            })

        has_non_sample = any(not s["source"].startswith("sample_") for s in snippets)
        if has_non_sample:
            snippets = [s for s in snippets if not s["source"].startswith("sample_")]

        return snippets[:k]
