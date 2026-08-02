"""sieve-agent — a minimal, transparent, local-first Sieve.

Four pillars, one module each:
  harness  → sieve_agent/runtime + sieve_agent/gateway  (scaffolding around the raw LLM)
  loop     → sieve_agent/loop                      (observe → reason → act → repeat)
             sieve_agent/graph                     (opt-in structure around the loop — extends this pillar)
  memory   → sieve_agent/memory                    (procedural / semantic / episodic)
  ops      → sieve_agent/ops + evals/              (trace → eval → gate → release)
"""

__version__ = "0.1.0"
