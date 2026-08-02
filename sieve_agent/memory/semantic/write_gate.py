"""The write-side gate — the novelty this library leads with.

Most agent memory tutorials (sieve-agent included) gate *retrieval*: "does this
turn need memory?" Nobody gates *writing*: every "remember that..." gets
appended, so the store fills with noise ("user said hi") that later pollutes
search results and consolidation.

This gate scores a CANDIDATE fact before it's ever inserted, on three axes:

  durability   is this a lasting fact (preference, relationship, project) or
               a transient one-off (small talk, a fleeting mood)?
  specificity  is there an actual subject + concrete content, or is it vague
               ("things are fine")?
  redundancy   does an existing active fact already say this?

Two implementations ship: `HeuristicWriteGate` (deterministic, no API calls,
fully unit-testable — the default) and `LLMWriteGate` (wraps it with one
small-model call for judgment calls the heuristic can't make, fails OPEN to
the heuristic's verdict on any error — same fail-open discipline sieve-agent's
retrieval gate uses).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Phrases that signal a passing, non-durable utterance rather than a fact
# worth keeping forever.
_TRANSIENT_PATTERNS = [
    r"^(hi|hello|hey|thanks|thank you|ok|okay|sure|cool|nice|got it|yep|yeah|no)\b",
    r"\bhow are you\b",
    r"\bwhat('?s| is) (up|new)\b",
    r"^(good|bad) (morning|afternoon|evening|night)$",
]
_DURABLE_HINTS = [
    "prefer", "always", "never", "birthday", "allerg", "works at", "lives in",
    "is my", "likes", "dislikes", "hates", "loves", "deadline", "anniversary",
    "phone number", "email is", "favorite", "favourite", "remember that",
    "don't like", "important:",
]


@dataclass
class Candidate:
    subject: str
    content: str
    source: str = "user"


@dataclass
class WriteDecision:
    store: bool
    confidence: float  # 0..1 — becomes the fact's `confidence` column if stored
    reason: str


class HeuristicWriteGate:
    """Deterministic, zero-dependency scorer. This is the load-bearing
    implementation — the LLM variant only refines its borderline calls."""

    def __init__(self, min_content_words: int = 3):
        self.min_content_words = min_content_words

    def score(self, candidate: Candidate, existing: list[str] | None = None) -> WriteDecision:
        text = candidate.content.strip()
        lower = text.lower()

        if not candidate.subject.strip() or not text:
            return WriteDecision(False, 0.0, "missing subject or content")

        if len(text.split()) < self.min_content_words and not any(h in lower for h in _DURABLE_HINTS):
            return WriteDecision(False, 0.1, "too short/vague to be a durable fact")

        for pattern in _TRANSIENT_PATTERNS:
            if re.search(pattern, lower):
                return WriteDecision(False, 0.05, "matches a transient/small-talk pattern")

        has_durable_hint = any(hint in lower for hint in _DURABLE_HINTS)

        if existing:
            for prior in existing:
                if _near_duplicate(lower, prior.lower()):
                    return WriteDecision(False, 0.2, "redundant with an existing fact")

        confidence = 0.9 if has_durable_hint else 0.6
        reason = "durable-language hint matched" if has_durable_hint else "specific subject + content, no red flags"
        return WriteDecision(True, confidence, reason)


def _near_duplicate(a: str, b: str, threshold: float = 0.8) -> bool:
    """Cheap redundancy check: token-set Jaccard overlap. Good enough to
    catch 'Alex likes tennis' vs 'Alex really likes tennis' without an
    embedding model."""
    ta, tb = set(re.findall(r"[a-z0-9]+", a)), set(re.findall(r"[a-z0-9]+", b))
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / len(ta | tb)
    return overlap >= threshold


class LLMWriteGate:
    """Wraps HeuristicWriteGate with one small-model call for judgment calls
    the heuristic is unsure about (confidence in the 0.4-0.7 band). Fails
    open to the heuristic's own verdict — a borrowed fact beats a lost one,
    same principle as sieve-agent's retrieval_gate.should_retrieve."""

    PROMPT = """\
You are a write-gate for a personal assistant's long-term memory. Decide if
this candidate fact is worth storing PERMANENTLY (a durable preference,
relationship, or project detail) versus discarding (small talk, a one-off,
something too vague to act on later).

Reply with ONLY this JSON: {{"store": true/false, "confidence": 0.0-1.0, "reason": "<5 words>"}}

Subject: {subject}
Content: {content}"""

    def __init__(self, client, model: str, base: HeuristicWriteGate | None = None):
        self.client = client
        self.model = model
        self.base = base or HeuristicWriteGate()

    def score(self, candidate: Candidate, existing: list[str] | None = None) -> WriteDecision:
        base_decision = self.base.score(candidate, existing)
        if not (0.4 <= base_decision.confidence <= 0.7):
            return base_decision  # heuristic was confident either way — trust it

        import json

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": self.PROMPT.format(
                    subject=candidate.subject, content=candidate.content)}],
            )
            text = "".join(b.text for b in response.content if b.type == "text")
            data = json.loads(text[text.index("{"): text.rindex("}") + 1])
            return WriteDecision(bool(data.get("store")), float(data.get("confidence", 0.5)),
                                  data.get("reason", "llm judgment"))
        except Exception as exc:
            return WriteDecision(base_decision.store, base_decision.confidence,
                                  f"llm gate failed open to heuristic ({type(exc).__name__})")
