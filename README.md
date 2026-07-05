# agent-harness

*Safety harness for AI agents — deterministic policy, budget, and audit around a probabilistic core. Runs anywhere: cloud or fully local, demoed over an Apache Iceberg lakehouse.*

## Quickstart

```bash
uv sync --all-extras           # install everything
cp .env.example .env           # add your API keys
uv run pytest tests/ evals/    # all tests green before first model call
```

## Architecture

```mermaid
flowchart TD
    U([User]) --> L[Agent Loop\nprobabilistic core]
    L --> HPC[pre_model_call\nbudget check . prompt log]
    HPC --> M((LiteLLM\nClaude . Gemini . Ollama))
    M --> HTC[pre_tool_call\npolicy gate\nALLOW . DENY . REQUIRE_APPROVAL]
    HTC --> T[Tools\nquery_data . describe_schema\ngenerate_report . create_ticket]
    T --> HPTC[post_tool_call\nPII redact . audit JSONL . cost accounting]
    HPTC --> L
    HTC --> |MCP| MCP[MCP stdio server\ndescribe_schema]
    MCP --> HPTC

    style L fill:#f9e4b7,stroke:#e0a800
    style HPC fill:#d4edda,stroke:#28a745
    style HTC fill:#d4edda,stroke:#28a745
    style HPTC fill:#d4edda,stroke:#28a745
    style M fill:#fff3cd,stroke:#ffc107
```

**Yellow = probabilistic core. Green = deterministic shell.**

## The Thesis

> The model is probabilistic. The enterprise's obligations are not.

The harness is a **deterministic shell of lifecycle hooks** around a **probabilistic core**.
Every policy decision, audit event, and cost check is computed in Python -- never in a prompt.
`harness/` never imports `agent/`: governance survives framework and model churn.

## Demo Scripts

```bash
make demo-determinism   # same risky prompt 3x -> model varies, hook = REQUIRE_APPROVAL always
make demo-policy        # create_ticket -> PENDING -> CLI approve -> audit chain printed
```

### Real GitHub issue (optional)

```bash
# 1. Set a fine-grained PAT (Issues: Read & Write, single repo)
# 2. Install the binary: brew install github-mcp-server
# 3. Add to .env:
#      TICKETS_BACKEND=github
#      GITHUB_PERSONAL_ACCESS_TOKEN=github_pat_...
#      GITHUB_REPO_OWNER=<you>
#      GITHUB_REPO_NAME=agent-harness
TICKETS_BACKEND=github make demo-policy
```

This creates a real GitHub issue after CLI approval — same policy gate, same
audit shape as the mock path. Air-gapped fallback: `TICKETS_BACKEND=mock` (default).

## Model Flip

```bash
DEFAULT_MODEL=ollama/qwen2.5:7b uv run python -c "
import asyncio, tools.echo
from agent.loop import run
print(asyncio.run(run('echo hello world')))
"
```

## Testing

```bash
make test       # unit tests (shell guarantees -- blocking)
make evals      # golden case evals (recorded responses -- blocking)
make ci         # lint + typecheck + test + evals
```

Mantra: *unit tests for guarantees, evals for capabilities.*

## Observability

```bash
make phoenix                    # launch Phoenix UI at localhost:6006
PHOENIX_ENABLED=true make demo  # agent sends OTel traces to Phoenix in real time
make evals-judge                # run LLM-as-judge faithfulness metric (local, non-blocking)
```

Instrumented via OpenTelemetry + OpenInference — backend-agnostic. Local JSONL
(`traces.jsonl`) is the always-on zero-dependency path.

## Stack

Python 3.12 · uv · Pydantic v2 · LiteLLM · DuckDB + Apache Iceberg · MCP · Phoenix (OTel) + local JSONL · pytest + phoenix-evals · ruff · mypy

See `docs/adr/` for all architectural decisions.

## Why No Containers

Nothing to orchestrate: DuckDB is embedded (a Python library, not a server),
Phoenix is a Python library launched in-process, the agent is a single process.
Reproducibility comes from `uv`'s lock file, not from an image.

```bash
uv sync --all-extras   # deterministic install from uv.lock
make generate-data     # create the Iceberg warehouse
make demo              # run everything
```
