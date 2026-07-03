# agent-harness

*A deterministic shell for probabilistic agents -- policy, budgets, audit, and evals around a swappable core. Demoed on a Data Ops agent over Apache Iceberg.*

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

## Stack

Python 3.12 . uv . Pydantic v2 . LiteLLM . DuckDB + Apache Iceberg . MCP . Langfuse + local JSONL . pytest + DeepEval . ruff . mypy

See `docs/adr/` for all architectural decisions.
