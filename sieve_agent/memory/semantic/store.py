"""Semantic memory — durable facts, keyword-searched with SQLite FTS5.

The Hermes insight from the whiteboard: "keyword top-k, no embedding". For a
single user's facts, ranked keyword search (BM25) is fast, fully local, and —
crucially for teaching — you can read the whole index with sqlite3.
Want vectors? Set SIEVE_SEMANTIC_STORE=supabase (see supabase_store.py).

Three things happen here that a plain "INSERT every fact" store doesn't do:

  write gate     (write_gate.py)     — score a candidate BEFORE it's stored;
                                        small talk and vague one-offs never
                                        make it into the index at all.
  contradiction  (contradiction.py)  — a new fact that disagrees with an
                                        existing one on the same subject +
                                        attribute SUPERSEDES it instead of
                                        sitting alongside it. Nothing is
                                        deleted — `timeline()` replays the
                                        full history.
  decay          (decay.py)          — search results are re-ranked by
                                        recency + access frequency, not pure
                                        BM25 rank, and `consolidate()` finds
                                        facts stale enough to archive.

sieve-agent's own retrieval_gate.py already gates reading ("does this turn
need memory?"). This is the write-side half of that idea.
"""

from __future__ import annotations

import re
import sqlite3

from sieve_agent.memory.semantic.contradiction import HeuristicConflictDetector
from sieve_agent.memory.semantic.decay import rerank, sweep_for_archival
from sieve_agent.memory.semantic.write_gate import Candidate, HeuristicWriteGate


def _fts_query(text: str) -> str:
    """User text isn't a valid FTS5 query (quotes/punctuation break MATCH).
    Reduce it to `word OR word OR ...` over alphanumeric tokens."""
    words = re.findall(r"[a-zA-Z0-9]{2,}", text.lower())
    return " OR ".join(dict.fromkeys(words)) if words else ""


class SqliteFactStore:
    def __init__(self, conn: sqlite3.Connection, write_gate=None, conflict_detector=None):
        self.conn = conn
        self.write_gate = write_gate or HeuristicWriteGate()
        self.conflict_detector = conflict_detector or HeuristicConflictDetector()

    # ---- write path: gate -> conflict check -> supersede-or-insert
    def add(self, subject: str, content: str, source: str = "user") -> str:
        """Returns a human-readable outcome: what was stored, rejected (and
        why), or superseded. Callers that only cared about the side effect
        (consolidation, evals) can keep ignoring the return value."""
        existing = self._active_for_subject(subject)
        decision = self.write_gate.score(Candidate(subject, content, source),
                                          [f["content"] for f in existing])
        if not decision.store:
            return f"not stored — {decision.reason}"

        conflict = self.conflict_detector.find_conflict(subject, content, existing)

        cur = self.conn.execute(
            "INSERT INTO facts (subject, content, source, confidence, previous_id) VALUES (?,?,?,?,?)",
            (subject.lower().strip(), content, source, decision.confidence,
             conflict.existing_id if conflict else None),
        )
        new_id = cur.lastrowid
        if conflict:
            self.conn.execute(
                "UPDATE facts SET status='superseded', superseded_by=? WHERE id=?",
                (new_id, conflict.existing_id),
            )
        self.conn.commit()
        if conflict:
            return f"stored (supersedes fact #{conflict.existing_id})"
        return f"stored (confidence={decision.confidence})"

    def _active_for_subject(self, subject: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, subject, content FROM facts WHERE status='active' AND subject=?",
            (subject.strip().lower(),),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- read path: FTS rank -> decay rerank -> bump access stats
    def search(self, query: str, top_k: int = 4) -> list[str]:
        hits = self._search_rows(query, top_k)
        return [f"[{r['subject']}] {r['content']}" for r in hits]

    def _search_rows(self, query: str, top_k: int) -> list[dict]:
        fts = _fts_query(query)
        if not fts:
            return []
        rows = self.conn.execute(
            "SELECT f.id, f.subject, f.content, f.confidence, f.last_accessed_at, f.access_count "
            "FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
            "WHERE facts_fts MATCH ? AND f.status='active' ORDER BY rank LIMIT ?",
            (fts, max(top_k * 3, top_k)),  # over-fetch by BM25 rank, decay rerank narrows it
        ).fetchall()
        hits = rerank([dict(r) for r in rows])[:top_k]
        for hit in hits:
            self.conn.execute(
                "UPDATE facts SET access_count = access_count + 1, last_accessed_at = datetime('now') WHERE id=?",
                (hit["id"],),
            )
        if hits:
            self.conn.commit()
        return hits

    # --- CRUD: humans (dashboard) and the agent (manage_memory tool) edit memory.
    # The facts_au / facts_ad triggers keep the FTS index in sync automatically.
    def list(self, limit: int = 200) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, subject, content, source, status, confidence, superseded_by, created_at "
            "FROM facts ORDER BY (status='active') DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_with_ids(self, query: str, top_k: int = 8) -> list[dict]:
        hits = self._search_rows(query, top_k)
        return hits or self.list(top_k)

    def timeline(self, subject: str) -> list[dict]:
        """Every version of a subject's facts, oldest first — the
        contradiction-resolution history (superseded -> active)."""
        rows = self.conn.execute(
            "SELECT id, content, status, source, confidence, created_at, superseded_by "
            "FROM facts WHERE subject=? ORDER BY created_at ASC",
            (subject.strip().lower(),),
        ).fetchall()
        return [dict(r) for r in rows]

    def update(self, fact_id: int, content: str, subject: str | None = None) -> bool:
        if subject is None:
            cur = self.conn.execute("UPDATE facts SET content=? WHERE id=?", (content, fact_id))
        else:
            cur = self.conn.execute(
                "UPDATE facts SET content=?, subject=? WHERE id=?",
                (content, subject.lower().strip(), fact_id),
            )
        self.conn.commit()
        return cur.rowcount > 0

    def delete(self, fact_id: int) -> bool:
        """A hard, explicit delete (the user/agent asked to forget this one
        specifically) — distinct from consolidate()'s soft archive of facts
        that merely decayed."""
        cur = self.conn.execute("DELETE FROM facts WHERE id=?", (fact_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # ---- consolidation: archive facts that decayed below threshold
    def consolidate(self) -> list[int]:
        rows = self.conn.execute(
            "SELECT id, confidence, last_accessed_at, access_count FROM facts WHERE status='active'"
        ).fetchall()
        stale_ids = sweep_for_archival([dict(r) for r in rows])
        for fact_id in stale_ids:
            self.conn.execute("UPDATE facts SET status='archived' WHERE id=?", (fact_id,))
        if stale_ids:
            self.conn.commit()
        return stale_ids
