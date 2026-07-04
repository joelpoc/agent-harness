# CLAUDE.md — agent-harness

**Repo name:** `agent-harness`
**Tagline (GitHub description + README subtitle):** *A deterministic shell for probabilistic agents — policy, budgets, audit, and evals around a swappable core. Demoed on a Data Ops agent over Apache Iceberg.*

## What this is

An **agent harness** built as the final interview exercise for a Senior Solutions Engineer – AI role at Cloudera (90-minute working session: walkthrough + live coding). It will be shared as a GitHub repo and demoed live. Deadline-driven: it must be demo-ready, clone-clean, and defensible in every design decision.

**Owner:** Joel — Senior AI Engineer & Cloud Architect. Python expert; runs LangGraph/Vertex/GKE agentic systems in production. Assume senior-level context; do not over-explain basics.

## The thesis (never violate this)

> The model is probabilistic. The enterprise's obligations are not.
> The harness is a **deterministic shell of lifecycle hooks** around a **probabilistic core** (the model + agent loop).

Every architectural decision serves this thesis:
1. **Deterministic guarantees live in hooks** (code), never in prompts.
2. **The shell never trusts the core.** Audit is recorded by the shell, not self-reported by the agent.
3. **`harness/` NEVER imports `agent/`.** The dependency direction is the argument: governance must survive framework/model churn. If a change requires harness→agent imports, the design is wrong — stop and reconsider.
4. **Facts are deterministic, language is probabilistic.** The LLM decides *what* to query and *how* to explain; SQL computes every number. The model never invents figures.

## Architecture

```
User → agent loop (probabilistic core, hand-rolled, ~80-120 lines)
         │ every model call / tool call passes through:
         ▼
   HOOK PIPELINE (deterministic shell)
   pre_model_call   → budget check (hard stop), prompt logging
   pre_tool_call    → policy gate: ALLOW / DENY / REQUIRE_APPROVAL (YAML, deny-by-default)
   post_tool_call   → PII redaction → audit event (JSONL) → cost accounting
   on_budget_exceeded → clean halt
   on_approval_needed → human-in-the-loop CLI prompt
         ▼
   TOOLS (Pydantic contracts, registry)
   native: query_data, generate_report, create_ticket, describe_schema
   via MCP: describe_schema also exposed by a local stdio MCP server,
            consumed through MCPToolAdapter → same contracts, same hooks
         ▼
   DATA: DuckDB reading Apache Iceberg tables (cloud billing/usage synthetic dataset)
```

## Directory layout

```
agent-harness/
├── CLAUDE.md                 # this file
├── README.md                 # quickstart, Mermaid architecture diagram, design opinions
├── docs/adr/                 # 001–007 — every non-obvious decision documented
├── pyproject.toml            # uv-managed, Python 3.12
├── harness/                  # THE DETERMINISTIC SHELL — no imports from agent/
│   ├── hooks.py              # hook chain: registration + execution order
│   ├── contracts.py          # Pydantic v2 tool contracts + registry (native + MCP)
│   ├── policy.py             # YAML policy engine, deny-by-default
│   ├── budget.py             # cost ceiling, accumulates LiteLLM cost metadata
│   ├── redact.py             # regex PII redaction (emails, IBAN, phone); Presidio noted as prod option
│   ├── audit.py              # JSONL audit events: who/what/args-hash/decision/tokens/cost/latency
│   ├── tracing.py            # OTel/Phoenix (optional) + local JSONL spans (always)
│   └── mcp_adapter.py        # MCPToolAdapter: discover → wrap in contract → register
├── agent/                    # THE PROBABILISTIC CORE — thin, swappable
│   ├── loop.py               # hand-rolled tool-use loop
│   └── models.py             # LiteLLM config: gemini / anthropic / ollama
├── tools/                    # one file per tool, contract-first
├── mcp_server/               # minimal stdio MCP server exposing describe_schema
├── data/                     # generate_dataset.py → Iceberg tables (duckdb iceberg ext)
├── policies/default.yaml     # includes stricter rules for mcp/* tools
├── evals/
│   ├── cases/                # 13 golden YAML cases
│   ├── test_evals.py         # runs against RECORDED model responses (blocking)
│   └── run_judge_metrics.py  # Phoenix Evals faithfulness metric (non-blocking, local)
├── tests/                    # unit tests for the shell (policy, budget, redact, hooks, audit)
├── scripts/                  # demo_run.py, demo_determinism.py, demo_policy.py, record_evals.py
└── .github/workflows/ci.yml  # ruff + mypy + pytest (unit BLOCKING, evals BLOCKING, judge NON-blocking)
```

## Stack (locked — do not substitute without asking)

- Python 3.12, **uv** (`uv sync --all-extras` must be the entire setup — no Docker)
- **Pydantic v2** — all contracts, configs, policies, eval cases are typed models
- **LiteLLM SDK** (not proxy) — model routing + per-call cost metadata
  - Primary: `gemini/gemini-2.5-flash` or `gemini/gemini-2.5-pro` via `GEMINI_API_KEY` (Google AI Studio, free tier)
  - Local flip: `ollama/qwen2.5:7b` (air-gapped demo path, 16GB RAM / 4.7GB model)
  - Optional: `anthropic/claude-sonnet-4-5` via `ANTHROPIC_API_KEY`
- **DuckDB** + **pyiceberg** — Iceberg is required for the demo (JD names it); Parquet only as documented fallback
- **MCP official Python SDK**, stdio transport only
  - Internal mock server (`mcp_server/`) — offline fallback, deny-by-default demo asset
  - **GitHub MCP server** (`github-mcp-server` binary) — real trust boundary demo; whitelist-only registration; fine-grained PAT (issues-only, single repo); see ADR 008
  - `TICKETS_BACKEND=mock|github` selects the ticketing backend; agent/policy/audit are unaware
- **Arize Phoenix** (local UI at `localhost:6006`) + **local JSONL spans** (always-on, zero-dep)
  - Instrumentation via **OpenTelemetry + OpenInference** — backend-agnostic, swap to any OTLP collector
  - Launch: `make phoenix` — no account needed
  - Langfuse is the production team-server choice (used in prod, not in this repo — see ADR 007)
- **pytest** (+ **arize-phoenix-evals** for 1–2 judge metrics, non-blocking), **ruff**, **mypy**
- No LangGraph, no CrewAI, no OPA, no OpenRouter, no MLflow, no Docker in this repo (deliberate — see ADRs)

## Testing doctrine

- **Shell = unit tests, blocking.** `assert policy.evaluate(create_ticket_call) == Decision.REQUIRE_APPROVAL`. Exhaustive on policy/budget/redaction/hook-ordering. These prove guarantees.
- **Core = evals, blocking but recorded.** 13 golden YAML cases: expected SQL semantics, expected policy decisions for adversarial prompts, expected refusals. CI runs against **recorded model responses** — never live API calls in CI (cost, flake, determinism).
- **Judge metrics (Phoenix Evals) = non-blocking.** 1–2 metrics (report faithfulness). Run locally with `make evals-judge`. CI uploads `judge_report.json` as artifact. They inform, never gate.
- **Mantra:** CI proves the shell with asserts; Phoenix measures the core with experiments. GitHub is where the gate lives, Phoenix is where the analysis lives.

## Conventions

- Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`); small, reviewable commits — the git history will be read by interviewers.
- Every non-obvious decision gets an ADR (short: context / decision / consequences).
- Type hints everywhere; `mypy --strict` on `harness/`.
- Docstrings state the *guarantee* a module provides, not just what it does.
- README must contain: the tagline as subtitle under the H1, 3-command quickstart, Mermaid architecture diagram (shell/core), the thesis in ≤5 lines, demo script section.
- English for all code, docs, commits.

## Build order (work through milestones in sequence)

1. **M1 — skeleton + contracts:** pyproject, layout, `contracts.py`, registry, one echo tool, loop stub that runs end-to-end with a fake model. CI green from the first commit.
2. **M2 — the shell:** hooks.py chain, policy.py + default.yaml, budget.py, redact.py, audit.py. Full unit-test coverage. This is the thesis — highest quality bar here.
3. **M3 — real core:** LiteLLM models.py (3 providers), hand-rolled loop with tool-use, tracing.py (OTel/Phoenix + local JSONL).
4. **M4 — data + tools:** dataset generator → Iceberg, query_data (text-to-SQL), describe_schema, generate_report, create_ticket.
5. **M5 — evals:** golden cases, recorded responses, CI wiring, Phoenix Evals non-blocking job.
6. **M6 — MCP:** stdio server + MCPToolAdapter + stricter `mcp/*` policy rules + demo of same-shell governance.
7. **M7 — demo polish:** README, ADRs, Mermaid, demo script, clean-clone test, rehearsal fixtures.

**Cut order if time compresses:** M6 MCP → Iceberg (→Parquet) → Phoenix UI (→local-only JSONL) → phoenix-evals. **Never cut:** hook pipeline, policy gate, audit log, CI tests+evals.

## Demo requirements (the code must make these trivial to perform live)

1. **Determinism made visible:** same risky prompt 3× → model output varies, hook decision identical (`REQUIRE_APPROVAL`, same audit shape). `make demo-determinism`.
2. **Policy block + human approval:** create_ticket → PENDING → CLI approve → executes → audit chain printed. `make demo-policy`.
3. **Model flip:** `DEFAULT_MODEL=ollama/qwen2.5:7b make demo` — one env var, everything else identical.
4. **MCP same-shell:** registry listing shows native + MCP tools; MCP call hits same policy/audit with stricter limits.
5. **Real GitHub issue:** `TICKETS_BACKEND=github make demo-policy` → CLI approve → real issue created in this repo → audit event identical to mock path. Demonstrates the harness governing a real third-party trust boundary.
6. **Air-gapped fallback:** `TICKETS_BACKEND=mock` (default) + `ollama/qwen2.5:14b` = fully offline demo. GitHub path is opt-in.
7. **Live-build slots:** adding a new tool must take <10 min on top of contracts; adding a `post_tool_call` hook (e.g., block salary columns) must take <10 lines. Keep these paths friction-free — they will be coded live in the interview.

## Hard guardrails for Claude Code

- Never put a number-producing computation in an LLM prompt path. SQL computes; the model narrates.
- Never bypass the hook pipeline "temporarily" for debugging convenience — fix the pipeline instead.
- Never add a dependency without an ADR justifying it against the "boring dependencies" principle.
- Keep the loop under ~120 lines. If it grows, extract into the shell or simplify — do not reach for a framework.
- No secrets in the repo, ever. `.env.example` documents required vars; config validated via Pydantic settings with clear error messages when missing.
- Everything must work offline except cloud model calls: `ollama` model + local JSONL traces must give a full air-gapped demo path. No internet dependency except the model API.
- No Docker. Reproducibility comes from `uv.lock`, not from an image layer.
