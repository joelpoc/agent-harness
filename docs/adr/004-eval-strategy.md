# ADR 004 — Eval Strategy: Recorded Responses + Non-Blocking Judge

## Context
Testing an LLM agent in CI has three failure modes:
1. **Live API calls**: flaky (rate limits, latency), expensive, non-deterministic — CI is unreliable
2. **No evals**: the agent's capability is untested
3. **Only judge metrics as gates**: a judge model disagreeing blocks unrelated changes

## Decision
Three-tier testing strategy:

1. **Shell unit tests (blocking)**: `pytest tests/` — no model, pure Python. Prove guarantees. Always fast, always deterministic.
2. **Golden case evals (blocking, recorded)**: `pytest evals/` — run against pre-recorded model responses (YAML fixtures). Test tool call ordering, SQL semantics, policy decisions. Never call live APIs in CI.
3. **Judge metrics (non-blocking)**: DeepEval `continue-on-error: true` CI job. Report faithfulness and other quality metrics. They inform; they never gate a merge.

## Consequences
- CI is fast and deterministic by default.
- Capability regressions are surfaced by evals without flakiness.
- The mantra is encoded in CI structure: *unit tests for guarantees, evals for capabilities*.
