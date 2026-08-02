"""Contradiction resolution — turn a bag of facts into a timeline.

Most agent memories just append: "Alex prefers mornings" today, "Alex prefers
evenings" three weeks later, and now retrieval returns both with no signal
about which is current. This module detects when a new fact and an existing
one are about the same *attribute* of the same subject but disagree, and
supersedes the old one instead of leaving a contradiction sitting in the
store.

Detection is category-based: both facts must match the same attribute
pattern (a preference, a location, an employer, ...) for the same subject,
and NOT be near-duplicates of each other, to count as a conflict. This is
deliberately narrower than semantic similarity — it only fires when the
facts are clearly about the same *kind* of thing, which keeps false positives
low without an embedding model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sieve_agent.memory.semantic.write_gate import _near_duplicate

_CATEGORY_PATTERNS: dict[str, str] = {
    "preference": r"\b(prefers?|likes?|loves?|favou?rite|hates?|dislikes?)\b",
    "location": r"\blives?\s+in\b",
    "employer": r"\bworks?\s+at\b",
    "birthday": r"\bbirthday\b",
    "contact": r"\b(phone\s+number|email)\b",
    "schedule": r"\b(mornings?|evenings?|afternoons?)\b",
}


def _categories(text: str) -> set[str]:
    lower = text.lower()
    return {name for name, pattern in _CATEGORY_PATTERNS.items() if re.search(pattern, lower)}


@dataclass
class Conflict:
    existing_id: int
    existing_content: str
    shared_categories: set[str]


class HeuristicConflictDetector:
    def find_conflict(self, subject: str, content: str, existing_facts: list[dict]) -> Conflict | None:
        """`existing_facts` is a list of {'id', 'subject', 'content'} rows,
        already filtered to the same subject and status='active'."""
        new_categories = _categories(content)
        if not new_categories:
            return None
        for fact in existing_facts:
            if fact["subject"].lower() != subject.lower():
                continue
            shared = new_categories & _categories(fact["content"])
            if not shared:
                continue
            if _near_duplicate(content.lower(), fact["content"].lower()):
                continue  # same fact restated, not a contradiction
            return Conflict(fact["id"], fact["content"], shared)
        return None
