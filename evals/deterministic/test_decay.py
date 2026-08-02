"""DETERMINISTIC EVAL — decay-aware relevance (sieve_agent/memory/semantic/decay.py).

Plain BM25 keyword rank (what the facts_fts index gives you for free) treats
a fact from a year ago exactly like one from this morning if the words match
equally well. relevance_score adds recency (exponential decay, a real
tunable half-life) and access frequency on top; rerank() blends that into
FTS hits, and sweep_for_archival() flags facts stale enough to archive at
consolidation time. All pure math — no model, no clock mocking beyond
passing an explicit `now`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sieve_agent.memory.semantic.decay import relevance_score, rerank, sweep_for_archival


def _iso(days_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()


def test_a_fresh_fact_outscores_a_stale_one_at_equal_confidence():
    now = datetime.now(UTC)
    fresh = relevance_score(_iso(0), confidence=1.0, access_count=0, now=now)
    stale = relevance_score(_iso(90), confidence=1.0, access_count=0, now=now)
    assert fresh > stale


def test_half_life_actually_halves_the_score():
    """half_life_days is a real, checkable number, not a vibe: a fact exactly
    one half-life old should score at ~half of a fresh one."""
    now = datetime.now(UTC)
    at_zero = relevance_score(_iso(0), confidence=1.0, access_count=0, now=now, half_life_days=30)
    at_half_life = relevance_score(_iso(30), confidence=1.0, access_count=0, now=now, half_life_days=30)
    assert abs(at_half_life - at_zero / 2) < 0.05


def test_frequently_accessed_facts_get_a_relevance_bonus():
    now = datetime.now(UTC)
    rare = relevance_score(_iso(10), confidence=0.6, access_count=0, now=now)
    frequent = relevance_score(_iso(10), confidence=0.6, access_count=20, now=now)
    assert frequent > rare


def test_rerank_can_flip_bm25_order_when_recency_disagrees():
    """This is the whole point: a stale fact that happens to rank #1 by
    keyword match must not beat a fresh, relevant one after reranking."""
    now = datetime.now(UTC)
    bm25_order = [
        {"id": 1, "last_accessed_at": _iso(200), "confidence": 1.0, "access_count": 0},
        {"id": 2, "last_accessed_at": _iso(1), "confidence": 0.6, "access_count": 0},
    ]
    ranked = rerank(bm25_order, now=now)
    assert ranked[0]["id"] == 2


def test_sweep_for_archival_flags_only_facts_below_threshold():
    now = datetime.now(UTC)
    facts = [
        {"id": 1, "last_accessed_at": _iso(0), "confidence": 1.0, "access_count": 0},    # fresh -> keep
        {"id": 2, "last_accessed_at": _iso(400), "confidence": 0.5, "access_count": 0},  # stale -> archive
    ]
    stale = sweep_for_archival(facts, now=now)
    assert stale == [2]
