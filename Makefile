.PHONY: install test lint typecheck demo-determinism demo-policy demo demo-live phoenix evals-judge generate-data

install:
	uv sync --all-extras

test:
	uv run pytest tests/ -v

evals:
	uv run pytest evals/ -v

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy harness/

ci: lint typecheck test evals

demo-determinism:
	@echo "=== Running same risky prompt 3x to show deterministic hook decisions ==="
	uv run python scripts/demo_determinism.py

demo-policy:
	@echo "=== Demo: create_ticket -> PENDING -> human approval -> audit chain ==="
	uv run python scripts/demo_policy.py

demo:
	uv run python scripts/demo_run.py

demo-live:
	uv run python scripts/demo_run.py --model gemini/gemini-2.5-pro

phoenix:
	uv run python -c "import phoenix as px; px.launch_app(); input('Phoenix running at http://localhost:6006 — press Enter to stop')"

generate-data:
	uv run python data/generate_dataset.py
