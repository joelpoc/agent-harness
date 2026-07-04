# ADR 007 — Arize Phoenix over Langfuse (via OpenTelemetry)

## Context

The repo originally used Langfuse for tracing. Langfuse is a good production
team-server for prompt management, cost dashboards, and user-session analytics.
It is what we run in production today on the Finaius platform.

For this demo repo the requirements are different:
- **Local-first** — the demo must run without an internet connection except for
  model API calls. Langfuse cloud requires a network round-trip per trace.
- **Private AI narrative** — a key interview argument is that the harness
  governs AI behaviour without externalising data. Sending spans to a third-party
  cloud service weakens that argument.
- **Visual trace explorer** — during a live demo, being able to open
  `localhost:6006` and show the agent's decision tree in a browser is more
  compelling than a Langfuse dashboard.
- **OTel decoupling** — instrumentation should not be coupled to a specific
  backend. If we instrument via OpenTelemetry, we can point to Phoenix today,
  Grafana Tempo tomorrow, or Jaeger in an air-gapped environment.

## Decision

Use **Arize Phoenix** as the local trace UI, instrumented via **OpenTelemetry
and OpenInference** (`openinference-instrumentation-litellm`).

The integration path:
1. `phoenix.otel.register(endpoint=OTLP_ENDPOINT)` — registers an OTLP/HTTP
   exporter. This is standard OTel SDK, not a Phoenix-proprietary call.
2. `LiteLLMInstrumentor().instrument()` — auto-instruments every LiteLLM call
   via the OpenInference semantic conventions.
3. Local JSONL (`traces.jsonl`) remains the always-on zero-dependency path.

Phoenix is only launched when `PHOENIX_ENABLED=true`. The agent never blocks
on a tracing failure.

## On Langfuse

Langfuse is not removed because it is bad — it is removed because it is the
wrong tool for this context:

| | **Phoenix (this repo)** | **Langfuse (production)** |
|---|---|---|
| Runs locally | yes | cloud SaaS (self-host available) |
| Visual trace explorer | yes | yes |
| Prompt management | no | yes |
| Cost per user/session | no | yes |
| OTel native | yes | partial |
| Best for | demo, dev, debugging | production monitoring, team collaboration |

The right answer in production is both: OTel instrumentation pointing at
whatever backend the team operates. This repo demonstrates the OTel path.

## Consequences

- `langfuse` removed from main dependencies — lighter install, no cloud keys needed.
- `harness/tracing.py` is simpler: one sink (local JSONL) always, one optional
  OTel sink. No Langfuse-specific SDK calls.
- Instrumentation is backend-agnostic — a single `PHOENIX_COLLECTOR_ENDPOINT`
  env var points to any OTLP-compatible collector.
- Air-gapped demo path works without any tracing config: local JSONL only.
