.PHONY: install test lint typecheck demo-determinism demo-policy demo demo-local demo-block demo-ticket demo-budget chat phoenix evals-judge upload-evals-phoenix record-evals generate-data

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

demo-local:
	@echo "=== Demo: air-gapped path with local Ollama model ==="
	uv run python scripts/demo_run.py --model ollama/qwen2.5:7b

demo-block:
	@echo "=== Demo: AST guard blocks DELETE/mutating SQL ==="
	uv run python scripts/demo_run.py --scenario block

demo-ticket:
	@echo "=== Demo: full flow query → report → create_ticket (REQUIRE_APPROVAL) ==="
	uv run python scripts/demo_run.py --scenario ticket

demo-budget:
	@echo "=== Demo: budget ceiling enforced by the shell ==="
	BUDGET_USD_LIMIT=0.001 uv run python scripts/demo_run.py --scenario budget

chat:
	uv run python scripts/chat.py

phoenix:
	uv run python -c "import phoenix as px; px.launch_app(); input('Phoenix running at http://localhost:6006 — press Enter to stop')"

record-evals:
	DEFAULT_MODEL=gemini/gemini-2.5-pro uv run python scripts/record_evals.py --force

evals-judge:
	uv run python evals/run_judge_metrics.py

upload-evals-phoenix:
	@echo "=== Uploading golden cases as Phoenix Dataset ==="
	uv run python scripts/upload_evals_to_phoenix.py

generate-data:
	uv run python data/generate_dataset.py
