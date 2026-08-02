# Architecture

The full system, with a file path on every box.

```mermaid
flowchart TB
    classDef persist fill:#1a1a1a,stroke:#888,color:#eee

    U["Message in<br/>(gateway/: cli · telegram · voice · dashboard)"] --> WM

    subgraph TURN["One turn — rebuilt fresh, then discarded"]
        WM["Working memory<br/>runtime/session.py: SOUL.md + memory + chat history"]
        WM --> GATE{{"retrieval_gate.py<br/>does this turn need memory?"}}
        GATE -.->|only if needed| SEM
        GATE -.->|only if needed| EPI
        WM --> LLM["LLM call — loop/models.py"]
        LLM -->|tool call| TOOLS["tools/<br/>create_event · save_note · send_message · ..."]
        TOOLS -->|result| LLM
        LLM -->|no more tool calls, or max_iterations| REPLY["Reply"]
    end

    REPLY --> U
    REPLY -->|log the exchange| DB[("state.db — one SQLite file")]:::persist

    subgraph MEMORY["What persists — sieve_agent/memory/"]
        SEM["semantic/<br/>facts: write gate, contradiction<br/>resolution, decay-ranked search"]:::persist
        EPI["episodic/<br/>dated summaries"]:::persist
        PROC["procedural/<br/>SKILL.md, loaded on keyword match"]:::persist
    end
    PROC -.-> WM
    DB --- SEM
    DB --- EPI
    DB -->|every N exchanges| CONS{{"consolidation.py"}} --> SEM
    CONS --> EPI

    subgraph OPS["Ops — sieve_agent/ops/ + evals/"]
        TRACE["tracing.py<br/>1 JSONL trace per run"]
        DET["evals/deterministic<br/>0/1, unit-test style"]
        JUDGE["evals/judge<br/>scored %, LLM-as-judge"]
        RGATE{{"release_gate.py"}}
        DET & JUDGE --> RGATE
    end
    TURN -.->|every event| TRACE
```

## Design decisions worth stealing

- **The gate before retrieval** (not retrieval on every turn): a cheap-model judge
  answers "does this message need the user's memory?" — saves latency and, more
  importantly, keeps irrelevant memories from biasing answers.
- **Consolidation is batched** ("after N chats"), asynchronous to the reply path,
  and loss-safe: if the summarizer fails, the chat log stays unconsolidated.
- **Deterministic evals and judge evals never mix.** One is a unit test, the other
  is a scored opinion. The release gate requires 100% of the first and a threshold
  on the second.
- **Every layer has a boring default and a documented upgrade** — FTS5 → pgvector,
  mock calendar → Google Calendar, JSONL → Phoenix/Langfuse. The default is always
  zero-signup.
- **Graphs wrap the loop, never replace it.** When a turn needs shape (parallel
  steps, explicit routing), an opt-in graph workflow (`sieve_agent/graph/`) arranges nodes
  around the untouched loop — the `full_agent` node IS `run_loop`. Routers are plain
  code reading state a model wrote; every failure fails open to the plain loop; the
  dashboard renders the topology from the engine's own `describe()` so the picture
  can't drift. See `docs/agent-graphs-design.md`.

## What this deliberately is not

Not a framework, not multi-agent, not production infrastructure. Still not
multi-agent even with graph workflows: a graph's `agent_node` is the same loop
invoked as one step, not peer-to-peer agent messaging — execution follows the
edges deterministically. It's meant to stay small enough to read end to end.
