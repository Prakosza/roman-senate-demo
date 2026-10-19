from server.rag import RAG, _clean_chunk


def test_clean_chunk_removes_footnote_and_page_markers():
    text = "Pompey crossed to Greece [56] with the consuls (43) [p. 12] and the Senate [vol. ii]."
    assert _clean_chunk(text) == "Pompey crossed to Greece with the consuls and the Senate."


def test_clean_chunk_keeps_ordinary_brackets_and_numbers():
    text = "In 49 B.C. the Senate (led by the consuls) acted."
    assert _clean_chunk(text) == text


class _FakeCollection:
    def __init__(self, docs, sources, distances):
        self._result = {
            "documents": [docs],
            "metadatas": [[{"source": s} for s in sources]],
            "distances": [distances],
        }
        self.last_n_results = None

    def query(self, query_texts, n_results, include):
        self.last_n_results = n_results
        return self._result


def _rag_with(collection, max_per_source=4, max_distance=1.45):
    # Skip __init__: no Chroma client or embedding API needed for retrieval logic.
    rag = RAG.__new__(RAG)
    rag.max_per_source = max_per_source
    rag.max_distance = max_distance
    rag._col = lambda name: collection
    return rag


def test_retrieve_overfetches_twice_k():
    col = _FakeCollection([], [], [])
    _rag_with(col).retrieve("caesar_collection", "query", k=5)
    assert col.last_n_results == 10


def test_retrieve_drops_chunks_past_distance_cutoff():
    col = _FakeCollection(["close", "far"], ["a.txt", "b.txt"], [0.5, 2.0])
    snippets = _rag_with(col, max_distance=1.0).retrieve("c", "q", k=5)
    assert [s["text"] for s in snippets] == ["close"]


def test_retrieve_skips_duplicates_ignoring_whitespace():
    col = _FakeCollection(["the same  text", "the same text", "other"], ["a.txt", "b.txt", "c.txt"], [0.1, 0.2, 0.3])
    snippets = _rag_with(col).retrieve("c", "q", k=5)
    assert [s["text"] for s in snippets] == ["the same  text", "other"]


def test_retrieve_caps_snippets_per_source():
    docs = ["one", "two", "three", "four"]
    col = _FakeCollection(docs, ["big_book.txt"] * 3 + ["letters.txt"], [0.1, 0.2, 0.3, 0.4])
    snippets = _rag_with(col, max_per_source=2).retrieve("c", "q", k=5)
    assert [s["text"] for s in snippets] == ["one", "two", "four"]
    assert [s["source"] for s in snippets] == ["big_book.txt", "big_book.txt", "letters.txt"]


def test_retrieve_returns_at_most_k():
    docs = [f"chunk {i}" for i in range(8)]
    col = _FakeCollection(docs, [f"{i}.txt" for i in range(8)], [0.1] * 8)
    assert len(_rag_with(col).retrieve("c", "q", k=3)) == 3
