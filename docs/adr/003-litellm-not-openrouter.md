# ADR 003 — LiteLLM SDK (Not OpenRouter or Direct SDKs)

## Context
The demo requires at least 3 model providers: Anthropic Claude, Vertex AI Gemini, and local Ollama. Options:
1. Direct Anthropic + Google + Ollama SDKs (3 integrations)
2. OpenRouter (proxy service)
3. LiteLLM SDK (local library)

## Decision
Use **LiteLLM SDK** (not the proxy, not OpenRouter).

Reasons:
- Single unified API across all 3 providers
- Per-call cost metadata in response (used by `budget.py`)
- No external proxy dependency — works offline with Ollama
- MIT licensed, actively maintained
- `model="anthropic/claude-sonnet-*"` to `model="ollama/qwen2.5:7b"` is a one-line change

## Consequences
- Model flip demo works as a single config change — no code changes.
- Cost tracking is reliable: LiteLLM populates `response._hidden_params["response_cost"]`.
- Air-gapped demo path: `ollama` + local traces, no external services.
