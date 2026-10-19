import asyncio
from types import SimpleNamespace

from server import debate
from server.debate import (
    HISTORY_TURNS,
    DebateManager,
    build_documents_block,
    build_messages,
    build_retrieval_query,
)

SNIPPETS = [
    {"text": "Caesar crossed the Rubicon.", "source": "suetonius.txt"},
    {"text": "The Senate declared him a public enemy.", "source": "plutarch.txt"},
]


def test_retrieval_query_on_first_turn_is_just_the_topic():
    assert build_retrieval_query("Rubicon legality", []) == "Topic: Rubicon legality"


def test_retrieval_query_uses_start_of_opponents_last_turn():
    long_turn = "word " * 100
    query = build_retrieval_query("Rubicon legality", [("Pompey", long_turn)])
    assert query.startswith("Topic: Rubicon legality\n")
    last_point = query.split(": ", 2)[2]
    assert len(last_point) <= 201
    assert last_point.endswith("…")


def test_documents_block_is_numbered_from_one():
    block = build_documents_block(SNIPPETS)
    assert '<document index="1">' in block
    assert "<source>plutarch.txt</source>" in block
    assert '<document index="3">' not in block


def test_documents_block_when_nothing_was_retrieved():
    assert "<empty/>" in build_documents_block([])


def test_first_turn_messages():
    messages = build_messages("Caesar", "SYSTEM", "Rubicon legality", [], SNIPPETS)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "<debate_topic>Rubicon legality</debate_topic>" in messages[0]["content"]
    assert messages[-1]["content"].startswith("<documents>")
    assert messages[-1]["content"].endswith("Open the debate on: Rubicon legality")


def test_history_is_seen_from_the_speakers_side():
    turns = [("Caesar", "c1"), ("Pompey", "p1"), ("Caesar", "c2"), ("Pompey", "p2")]

    caesar = build_messages("Caesar", "S", "t", turns, [])
    assert [(m["role"], m["content"]) for m in caesar[1:-1]] == [
        ("assistant", "c1"),
        ("user", "p1"),
        ("assistant", "c2"),
        ("user", "p2"),
    ]
    assert caesar[-1]["content"].endswith("Now respond to Pompey's latest argument.")

    pompey = build_messages("Pompey", "S", "t", turns, [])
    assert [m["role"] for m in pompey[1:-1]] == ["user", "assistant", "user", "assistant"]
    assert pompey[-1]["content"].endswith("Now respond to Caesar's latest argument.")


def test_history_is_capped():
    turns = [("Caesar" if i % 2 == 0 else "Pompey", f"turn {i}") for i in range(HISTORY_TURNS + 10)]
    messages = build_messages("Caesar", "S", "t", turns, [])
    history = messages[1:-1]
    assert len(history) == HISTORY_TURNS
    assert history[-1]["content"] == f"turn {HISTORY_TURNS + 9}"


class _FakeStream:
    def __init__(self, tokens):
        self._chunks = [SimpleNamespace(choices=[])]  # e.g. a usage-only chunk
        self._chunks += [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=t))]) for t in tokens]
        self.closed = False

    def __iter__(self):
        return iter(self._chunks)

    def close(self):
        self.closed = True


class _FakeClient:
    def __init__(self, tokens):
        self.tokens = tokens
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return _FakeStream(self.tokens)


class _FakeRAG:
    def __init__(self):
        self.collections = []

    def retrieve(self, collection, query, k):
        self.collections.append(collection)
        return SNIPPETS


async def _drain(queue):
    items = []
    while True:
        item = await queue.get()
        items.append(item)
        if item == "[DEBATE_DONE]":
            return items


def test_debate_streams_turns_with_control_markers(tmp_path, monkeypatch):
    monkeypatch.setattr(debate, "LOG_DIR", tmp_path)
    monkeypatch.setattr(debate, "LOG_PATH", tmp_path / "debate.log")
    rag = _FakeRAG()
    client = _FakeClient(["Hello", " Senate."])
    manager = DebateManager(rag=rag, openai_client=client, model="test-model", max_turns=2, turn_delay=0)

    async def run():
        state = await manager.start_debate("chat-1", "Rubicon legality")
        return state, await _drain(state.queue)

    state, items = asyncio.run(run())

    assert items == [
        "[START:Caesar]",
        "Hello",
        " Senate.",
        "[END_TURN]",
        "[START:Pompey]",
        "Hello",
        " Senate.",
        "[END_TURN]",
        "[DEBATE_DONE]",
    ]
    assert state.turns == [("Caesar", "Hello Senate."), ("Pompey", "Hello Senate.")]
    assert rag.collections == ["caesar_collection", "pompey_collection"]
    assert not manager.is_active("chat-1")
    assert all(r["model"] == "test-model" and r["stream"] for r in client.requests)


def test_debate_error_is_reported_and_ends_the_debate(tmp_path, monkeypatch):
    monkeypatch.setattr(debate, "LOG_DIR", tmp_path)
    monkeypatch.setattr(debate, "LOG_PATH", tmp_path / "debate.log")

    class _BrokenClient:
        chat = SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        )

    manager = DebateManager(rag=_FakeRAG(), openai_client=_BrokenClient(), model="m", max_turns=2, turn_delay=0)

    async def run():
        state = await manager.start_debate("chat-1", "t")
        return await _drain(state.queue)

    items = asyncio.run(run())
    assert items[-2:] == ["[ERROR] boom", "[DEBATE_DONE]"]
