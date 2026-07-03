FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev extras in prod image)
RUN uv sync --frozen --no-dev

# Copy source
COPY harness/ harness/
COPY agent/ agent/
COPY tools/ tools/
COPY mcp_server/ mcp_server/
COPY data/ data/
COPY policies/ policies/
COPY scripts/ scripts/
COPY evals/ evals/

# Generate dataset at build time
RUN uv run python data/generate_dataset.py

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "python", "scripts/demo_run.py", "--no-live"]
