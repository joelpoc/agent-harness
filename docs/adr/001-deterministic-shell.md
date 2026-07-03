# ADR 001 — Deterministic Shell Architecture

## Context
Enterprise AI systems face a fundamental tension: LLMs are probabilistic and non-deterministic, but enterprise obligations (audit, compliance, cost control, security) are deterministic requirements. Mixing governance logic into prompts means governance can fail whenever the model fails.

## Decision
We separate the system into two layers:
- **Probabilistic core** (`agent/`): the model + tool-use loop. Thin and swappable.
- **Deterministic shell** (`harness/`): lifecycle hooks that intercept every model call and tool call.

The shell enforces all enterprise guarantees in code. The core is responsible only for language tasks.

Critical constraint: `harness/` **never** imports from `agent/`. Dependency direction is `agent -> harness`. This ensures governance is not coupled to model framework choice.

## Consequences
- Replacing the model (Claude -> Gemini -> Ollama) requires changes only in `agent/models.py` and the loop prompt; zero changes to governance.
- All audit, policy, and budget logic is unit-testable without a running model.
- The architecture argument for the interview is made structural, not rhetorical.
