# ADR 002 — Hand-Rolled Agent Loop (No Framework)

## Context
LangGraph, CrewAI, and similar frameworks provide agent loop abstractions. Using one would reduce boilerplate but introduce a dependency between the shell and the framework's hook/callback system.

## Decision
The agent loop is hand-rolled in ~80-120 lines (`agent/loop.py`). It handles:
- LiteLLM completion call
- Tool call extraction from response
- Hook dispatch (pre/post tool call)
- Message accumulation

No framework.

## Consequences
- The loop is readable and debuggable in a single file — important for a live interview walkthrough.
- Hook integration is explicit: the reviewer can trace every `await hooks.fire_*` call.
- Adding a new hook type is a one-file change in `harness/hooks.py`.
- The shell's independence from the core is structurally enforced, not just claimed.
- Trade-off: parallel tool call execution requires manual implementation (acceptable for this scope).
