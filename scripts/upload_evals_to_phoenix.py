"""
upload_evals_to_phoenix.py — uploads golden cases as a Phoenix Dataset and
runs an experiment with LLM evaluators so scores appear in the Phoenix UI.

After running, open http://localhost:6006/datasets to see:
  - The dataset with all 13 golden cases
  - An experiment run with faithfulness + sql_relevance scores per row

Usage:
    make phoenix                 # must be running first
    make upload-evals-phoenix
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

CASES_DIR = Path(__file__).parent.parent / "evals" / "cases"
DATASET_NAME = "agent-harness-evals"
PHOENIX_URL = "http://localhost:6006"
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini/gemini-2.5-pro")

FAITHFULNESS_TEMPLATE = """
You are evaluating whether an AI assistant's answer is grounded in SQL queries.
The assistant must derive all numbers from query_data tool calls — never invent figures.

[User question]
{question}

[SQL queries executed]
{reference}

[Assistant's final answer]
{output}

Does the answer appear consistent with having run those SQL queries?
Answer with exactly one word: "faithful" or "hallucinated"
""".strip()

SQL_RELEVANCE_TEMPLATE = """
You are evaluating whether a SQL query correctly addresses a user's question
about GCP cloud billing data.

[User question]
{question}

[Generated SQL]
{sql}

Does this SQL retrieve the data needed to answer the question?
Answer with exactly one word: "relevant" or "irrelevant"
""".strip()


def _probe_phoenix() -> None:
    import urllib.request

    try:
        urllib.request.urlopen(f"{PHOENIX_URL}/health", timeout=3)
    except Exception:
        print(f"✗ Phoenix not reachable at {PHOENIX_URL}")
        print("  Start it first:  make phoenix")
        sys.exit(1)


def _load_cases() -> list[dict[str, Any]]:
    cases = []
    for f in sorted(CASES_DIR.glob("*.yaml")):
        case = yaml.safe_load(f.read_text())
        if case.get("recorded_response"):
            cases.append(case)
    if not cases:
        print("No recorded cases found. Run: make record-evals")
        sys.exit(1)
    return cases


def _upload_dataset(client: Any, cases: list[dict[str, Any]]) -> Any:
    inputs = []
    outputs = []
    metadata = []

    for case in cases:
        recorded = case["recorded_response"]
        tool_calls = recorded.get("tool_calls", [])
        sql_queries = [
            str(tc.get("args", {}).get("sql", ""))
            for tc in tool_calls
            if tc.get("tool") == "query_data" and tc.get("args", {}).get("sql")
        ]
        inputs.append({"question": str(case["user_message"])})
        outputs.append({"answer": str(recorded.get("final_answer", ""))})
        metadata.append(
            {
                "id": case["id"],
                "sql_queries": "\n\n---\n\n".join(sql_queries),
                "adversarial": str(case.get("adversarial", False)),
            }
        )

    dataset = client.datasets.create_dataset(
        name=DATASET_NAME,
        inputs=inputs,
        outputs=outputs,
        metadata=metadata,
        dataset_description=(
            "Golden eval cases for agent-harness. "
            "Each row: user question + recorded SQL queries + final answer."
        ),
    )
    print(f"  ✓ Dataset '{DATASET_NAME}' created ({len(cases)} rows, id: {dataset.id})")
    return dataset


def _make_faithfulness_fn(llm: Any) -> Any:
    """Return a per-row faithfulness evaluator function for run_experiment."""
    from phoenix.evals import create_classifier, evaluate_dataframe

    classifier = create_classifier(
        name="faithfulness",
        prompt_template=FAITHFULNESS_TEMPLATE,
        llm=llm,
        choices=["faithful", "hallucinated"],
    )

    def faithfulness_eval(output: Any, example: Any) -> float:
        import pandas as pd

        reference = example.metadata.get("sql_queries", "")
        answer = output.get("answer", "") if isinstance(output, dict) else str(output)
        if not reference or not answer:
            return 0.0
        row_df = pd.DataFrame(
            [
                {
                    "question": example.input.get("question", ""),
                    "reference": reference,
                    "output": answer,
                }
            ]
        )
        results = evaluate_dataframe(dataframe=row_df, evaluators=[classifier], hide_tqdm_bar=True)
        score_col = next((c for c in results.columns if c.endswith("_score")), None)
        if not score_col:
            return 0.0
        score_obj = results[score_col].iloc[0]
        label = score_obj.get("label", "") if isinstance(score_obj, dict) else ""
        return 1.0 if label == "faithful" else 0.0

    return faithfulness_eval


def _make_sql_relevance_fn(llm: Any) -> Any:
    """Return a per-row sql_relevance evaluator function for run_experiment."""
    from phoenix.evals import create_classifier, evaluate_dataframe

    classifier = create_classifier(
        name="sql_relevance",
        prompt_template=SQL_RELEVANCE_TEMPLATE,
        llm=llm,
        choices=["relevant", "irrelevant"],
    )

    def sql_relevance_fn(output: Any, example: Any) -> float:
        import pandas as pd

        sql = example.metadata.get("sql_queries", "")
        if not sql:
            return 0.0
        row_df = pd.DataFrame(
            [
                {
                    "question": example.input.get("question", ""),
                    "sql": sql,
                }
            ]
        )
        results = evaluate_dataframe(dataframe=row_df, evaluators=[classifier], hide_tqdm_bar=True)
        score_col = next((c for c in results.columns if c.endswith("_score")), None)
        if not score_col:
            return 0.0
        score_obj = results[score_col].iloc[0]
        label = score_obj.get("label", "") if isinstance(score_obj, dict) else ""
        return 1.0 if label == "relevant" else 0.0

    return sql_relevance_fn


def main() -> None:
    _probe_phoenix()
    print(f"Phoenix: {PHOENIX_URL}")
    print(f"Judge model: {JUDGE_MODEL}")
    print()

    from phoenix.client import Client
    from phoenix.evals import LLM

    client = Client(base_url=PHOENIX_URL)
    cases = _load_cases()
    print(f"Loaded {len(cases)} golden cases")

    dataset = _upload_dataset(client, cases)

    llm = LLM(provider="litellm", model=JUDGE_MODEL)
    faithfulness_eval = _make_faithfulness_fn(llm)
    sql_relevance_eval = _make_sql_relevance_fn(llm)

    def task(example: Any) -> dict[str, Any]:
        return {
            "answer": example.output.get("answer", ""),
            "sql": example.metadata.get("sql_queries", ""),
        }

    print(f"  Running experiment 'judge-metrics' with {JUDGE_MODEL} ...")
    client.experiments.run_experiment(
        dataset=dataset,
        task=task,
        evaluators=[faithfulness_eval, sql_relevance_eval],
        experiment_name="judge-metrics",
        experiment_description="LLM-as-judge: faithfulness + sql_relevance on golden cases",
        print_summary=True,
    )

    print()
    print(f"✓ Done. View results: {PHOENIX_URL}/datasets")
    print("  Click 'agent-harness-evals' → Experiments tab → 'judge-metrics'")


if __name__ == "__main__":
    main()
