"""DETERMINISTIC EVAL — contradiction resolution (sieve_agent/memory/semantic/contradiction.py).

Without this, "Alex prefers mornings" and "Alex prefers evenings" (told three
weeks apart) both sit in the facts table forever, and gated_retrieve()
returns BOTH with no signal about which is current — the model has to guess.
HeuristicConflictDetector fires only when a new fact and an existing one
share the same subject AND the same attribute category (preference,
location, employer, ...); store.add() then supersedes the old one instead of
appending a contradiction. Nothing is deleted — timeline() replays the full
history in order.
"""

from __future__ import annotations

from sieve_agent.memory.semantic.contradiction import HeuristicConflictDetector


def detector():
    return HeuristicConflictDetector()


def test_a_new_preference_conflicts_with_an_old_one_for_the_same_subject():
    existing = [{"id": 1, "subject": "alex", "content": "Alex prefers morning meetings"}]
    conflict = detector().find_conflict("alex", "Alex prefers evening meetings now", existing)
    assert conflict is not None
    assert conflict.existing_id == 1
    assert "preference" in conflict.shared_categories


def test_different_subjects_never_conflict():
    existing = [{"id": 1, "subject": "raj", "content": "Raj prefers morning games"}]
    conflict = detector().find_conflict("alex", "Alex prefers evening meetings", existing)
    assert conflict is None


def test_unrelated_attribute_categories_are_not_a_conflict():
    """Same subject, different KIND of fact — an employer fact and a
    preference fact about Alex don't contradict each other."""
    existing = [{"id": 1, "subject": "alex", "content": "Alex works at Acme Corp"}]
    conflict = detector().find_conflict("alex", "Alex prefers evening meetings", existing)
    assert conflict is None


def test_restating_the_same_fact_is_not_a_conflict():
    """Near-duplicates (the write gate's own redundancy check) must not also
    register as a contradiction — that would supersede a fact with itself."""
    existing = [{"id": 1, "subject": "alex", "content": "Alex prefers morning meetings"}]
    conflict = detector().find_conflict("alex", "Alex prefers morning meetings", existing)
    assert conflict is None


def test_only_the_matching_category_conflicts_among_several_facts():
    existing = [
        {"id": 1, "subject": "alex", "content": "Alex prefers morning meetings"},
        {"id": 2, "subject": "alex", "content": "Alex lives in Seattle"},
    ]
    conflict = detector().find_conflict("alex", "Alex prefers evening meetings", existing)
    assert conflict.existing_id == 1
