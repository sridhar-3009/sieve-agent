"""Decay-aware relevance — memory that self-curates instead of growing forever.

Pure keyword rank (BM25, what sieve-agent's semantic store uses) treats a fact
from a year ago exactly like one from this morning as long as the words
match. That's wrong for a personal assistant: a stale preference should sink,
and one nobody's touched in months is a pruning candidate. This module adds
one scalar per fact — a relevance score built from recency and access
frequency — that re-ranks search hits and, separately, flags facts to
archive at consolidation time.

    relevance = confidence * exp(-ln(2) * days_since_access / half_life_days)
                + access_bonus(access_count)

Exponential decay means "half-life" is a real, tunable number (default 30
days: a fact untouched for a month is worth half of one touched today), not
a magic constant.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

DEFAULT_HALF_LIFE_DAYS = 30.0
ARCHIVE_THRESHOLD = 0.05  # relevance below this at consolidation time -> archive


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=UTC)


def relevance_score(
    last_accessed_at: str,
    confidence: float,
    access_count: int,
    now: datetime | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> float:
    now = now or datetime.now(UTC)
    days_idle = max(0.0, (now - _parse(last_accessed_at)).total_seconds() / 86400)
    recency = confidence * math.exp(-math.log(2) * days_idle / half_life_days)
    access_bonus = math.log1p(access_count) * 0.05  # frequently-touched facts get a small floor
    return round(recency + access_bonus, 4)


def rerank(rows: list[dict], now: datetime | None = None, half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> list[dict]:
    """Blend FTS rank order (rows already sorted by BM25) with relevance:
    each row gets a `relevance` key, and the list is re-sorted by it. Rows
    must have last_accessed_at/confidence/access_count columns."""
    for row in rows:
        row["relevance"] = relevance_score(
            row["last_accessed_at"], row["confidence"], row["access_count"], now, half_life_days
        )
    return sorted(rows, key=lambda r: r["relevance"], reverse=True)


def sweep_for_archival(
    facts: list[dict], now: datetime | None = None, half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    threshold: float = ARCHIVE_THRESHOLD,
) -> list[int]:
    """Returns ids of active facts whose relevance has decayed below
    `threshold` — consolidation calls this and archives (never hard-deletes)
    them, so a mistaken prune is always recoverable."""
    stale = []
    for fact in facts:
        score = relevance_score(fact["last_accessed_at"], fact["confidence"], fact["access_count"], now, half_life_days)
        if score < threshold:
            stale.append(fact["id"])
    return stale
