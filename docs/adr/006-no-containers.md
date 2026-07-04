# ADR 006 — No Containers

## Context

Early versions of this repo included a Dockerfile and docker-compose.yml. The
rationale was "reproducibility" and "one-command setup". But examining the
actual services:

- **DuckDB** — a Python library. It is not a server. There is no port, no
  process to start, no container needed.
- **Arize Phoenix** — a Python library that launches an HTTP server in-process
  (`px.launch_app()`). It can run in Docker, but it doesn't need to.
- **The agent** — a single async Python process. Interactive (human-in-the-loop
  approval prompts). Containers add friction to interactive demos.

The only thing Docker was adding was a second way to run the same code, with
the extra complexity of bind-mounting JSONL files and forwarding ports.

## Decision

Remove Docker entirely. Reproducibility is provided by `uv.lock` — a
cryptographically-pinned lock file committed to the repo. Every `uv sync`
on any machine produces the exact same environment.

Setup is three commands:

```bash
uv sync --all-extras
make generate-data
make demo
```

## Consequences

- No Dockerfile to maintain or update when dependencies change.
- No "works in Docker but not locally" debugging surface.
- The repo is simpler and the design argument is cleaner: the unit of
  reproducibility is the `uv.lock`, not an image layer.
- If a production deployment needed containerisation, adding a Dockerfile
  would be trivial. That is a deployment concern, not a demo concern.
