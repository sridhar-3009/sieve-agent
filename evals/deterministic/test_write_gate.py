"""DETERMINISTIC EVAL — the write-side gate (sieve_agent/memory/semantic/write_gate.py).

sieve-agent's own retrieval_gate.py already answers "does this turn need
memory?" before reading. Nothing answered "is this candidate worth writing?"
before this file — every save_note call landed in the store unconditionally,
so small talk ("hey what's up") sat in the facts table next to real
preferences forever. HeuristicWriteGate is the deterministic scorer that
runs before every insert now (see SqliteFactStore.add in store.py).

Fully offline — no model call, no ScriptedClient needed for the default
path. LLMWriteGate (a thin wrapper for borderline heuristic calls) is a
separate, opt-in class and isn't exercised here.
"""

from __future__ import annotations

from sieve_agent.memory.semantic.write_gate import Candidate, HeuristicWriteGate


def gate():
    return HeuristicWriteGate()


def test_small_talk_is_rejected():
    decision = gate().score(Candidate("user", "hey how are you"))
    assert decision.store is False


def test_missing_subject_or_content_is_rejected():
    assert gate().score(Candidate("", "some content here")).store is False
    assert gate().score(Candidate("user", "")).store is False


def test_short_vague_content_without_a_durable_hint_is_rejected():
    decision = gate().score(Candidate("alex", "ok fine"))
    assert decision.store is False
    assert "short" in decision.reason or "vague" in decision.reason


def test_a_durable_preference_is_stored_with_high_confidence():
    decision = gate().score(Candidate("alex", "Alex prefers morning meetings over afternoon ones"))
    assert decision.store is True
    assert decision.confidence >= 0.8


def test_a_specific_fact_without_a_durable_keyword_still_stores():
    """Durable-language hints (prefers/allergic to/...) boost confidence but
    aren't required — a concrete, specific sentence is enough on its own."""
    decision = gate().score(Candidate("project x", "Project X ships to production next quarter"))
    assert decision.store is True


def test_a_near_duplicate_of_an_existing_fact_is_rejected_as_redundant():
    existing = ["Alex really likes playing tennis on weekends"]
    decision = gate().score(Candidate("alex", "Alex likes playing tennis on weekends"), existing=existing)
    assert decision.store is False
    assert "redundant" in decision.reason


def test_a_related_but_distinct_fact_about_the_same_subject_still_stores():
    """Redundancy is token-overlap, not subject match — two different facts
    about Alex must not collide just because they share a subject."""
    existing = ["Alex prefers morning meetings"]
    decision = gate().score(Candidate("alex", "Alex is allergic to peanuts"), existing=existing)
    assert decision.store is True
