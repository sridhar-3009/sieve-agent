"""DETERMINISTIC EVAL — SqliteFactStore wiring (sieve_agent/memory/semantic/store.py).

The unit files (test_write_gate.py, test_contradiction.py, test_decay.py)
each pin one module in isolation. This one pins the thing that actually
matters end to end: does .add() really refuse noise, really supersede a
contradicted fact, and does .search() really come back decay-reranked and
free of superseded rows? These are the same guarantees save_note (the
model-facing tool) and gated_retrieve (the read path) depend on.
"""

from __future__ import annotations

import pytest

from sieve_agent.db import connect
from sieve_agent.memory.semantic.store import SqliteFactStore


@pytest.fixture
def store(tmp_path):
    return SqliteFactStore(connect(tmp_path))


def test_add_rejects_small_talk(store):
    outcome = store.add("user", "hey what's up")
    assert "not stored" in outcome
    assert store.list() == []


def test_add_stores_a_durable_fact(store):
    outcome = store.add("alex", "Alex prefers morning meetings")
    assert "stored" in outcome
    rows = store.list()
    assert len(rows) == 1
    assert rows[0]["status"] == "active"


def test_add_supersedes_a_contradicting_fact_and_keeps_the_timeline(store):
    store.add("alex", "Alex prefers morning meetings")
    outcome = store.add("alex", "Alex prefers evening meetings now")
    assert "supersedes" in outcome

    timeline = store.timeline("alex")
    assert [row["status"] for row in timeline] == ["superseded", "active"]
    assert timeline[0]["content"] == "Alex prefers morning meetings"
    assert timeline[1]["content"] == "Alex prefers evening meetings now"


def test_search_never_returns_a_superseded_fact(store):
    store.add("alex", "Alex prefers morning meetings")
    store.add("alex", "Alex prefers evening meetings now")

    hits = store.search("alex meetings")
    assert len(hits) == 1
    assert "evening" in hits[0]
    assert "morning" not in hits[0]


def test_search_bumps_access_count_for_dashboard_and_decay(store):
    store.add("alex", "Alex prefers morning meetings")
    store.search("alex meetings")
    row = store.list()[0]
    fact_id = row["id"]
    count = store.conn.execute("SELECT access_count FROM facts WHERE id=?", (fact_id,)).fetchone()[0]
    assert count == 1


def test_consolidate_archives_stale_facts_without_deleting_them(store):
    store.add("alex", "Alex prefers morning meetings")
    fact_id = store.list()[0]["id"]
    store.conn.execute(
        "UPDATE facts SET last_accessed_at = datetime('now', '-400 days'), confidence = 0.3 WHERE id=?",
        (fact_id,),
    )
    store.conn.commit()

    archived = store.consolidate()
    assert archived == [fact_id]
    assert store.search("alex meetings") == []  # gone from retrieval...
    row = store.conn.execute("SELECT status FROM facts WHERE id=?", (fact_id,)).fetchone()
    assert row["status"] == "archived"           # ...but never deleted


def test_explicit_delete_is_a_hard_delete_unlike_consolidate(store):
    store.add("alex", "Alex prefers morning meetings")
    fact_id = store.list()[0]["id"]
    assert store.delete(fact_id) is True
    row = store.conn.execute("SELECT * FROM facts WHERE id=?", (fact_id,)).fetchone()
    assert row is None
