"""save_note — writes a durable fact into semantic memory, on request.

This is the *explicit* memory path ("remember that Alex prefers mornings").
The *implicit* path is consolidation (sieve_agent/memory/consolidation.py), which
distills facts out of chat history without being asked.

Routes through Memory.facts.add() rather than inserting directly, so the
write gate and contradiction resolution (sieve_agent/memory/semantic/store.py)
apply here too — the model finds out, in the tool result, if what it just
tried to save was too vague to keep or quietly superseded an older fact.
"""

from __future__ import annotations

from sieve_agent.memory import Memory
from sieve_agent.tools.registry import Tool


def make_tool(memory: Memory) -> Tool:
    def save_note(subject: str, content: str) -> str:
        # SqliteFactStore.add() reports its write-gate verdict as a string;
        # other backends (SupabaseFactStore) return None and never reject.
        outcome = memory.facts.add(subject, content, source="user") or "stored"
        return f"'{subject}': {content} -> {outcome}"

    return Tool(
        name="save_note",
        description=(
            "Save a durable fact to long-term memory. Use when the user tells you something "
            "worth remembering about themselves, a person, or a project — especially if they "
            "say 'remember' or share a preference."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Who/what this is about, e.g. 'alex' or 'acme-project'"},
                "content": {"type": "string", "description": "The fact, one sentence"},
            },
            "required": ["subject", "content"],
        },
        fn=save_note,
    )
