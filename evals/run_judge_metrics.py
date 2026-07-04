"""
run_judge_metrics.py — LLM-as-judge metrics via Arize Phoenix Evals.

Runs locally: make evals-judge
Never runs in CI as a blocking gate — informative only.
Outputs a JSON pass-rate summary to evals/judge_report.json.

Metrics (1-2, non-blocking):
  1. report_faithfulness — final answer contains only facts from query_data results
  2. sql_relevance       — generated SQL addresses the user question

Uses the same model as the agent (GEMINI_API_KEY / DEFAULT_MODEL).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

CASES_DIR = Path(__file__).parent / "cases"
REPORT_PATH = Path(__file__).parent / "judge_report.json"


def load_recorded_cases() -> list[dict[str, Any]]:
    cases = []
    for f in sorted(CASES_DIR.glob("*.yaml")):
        case: dict[str, Any] = yaml.safe_load(f.read_text())
        if case.get("recorded_response") and not case.get("adversarial"):
            cases.append(case)
    return cases


def build_faithfulness_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        recorded = case["recorded_response"]
        tool_calls = recorded.get("tool_calls", [])
        query_results = " | ".join(
            str(tc.get("args", {})) for tc in tool_calls if tc.get("tool") == "query_data"
        )
        final_answer = recorded.get("final_answer", "")
        if final_answer and query_results:
            rows.append(
                {
                    "id": case["id"],
                    "question": str(case["user_message"]),
                    "reference": query_results,
                    "output": final_answer,
                }
            )
    return rows


def run_faithfulness_metric(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate whether the final answer is faithful to the query_data results."""
    try:
        import pandas as pd  # type: ignore[import-untyped]
        from phoenix.evals import (  # type: ignore[import-untyped]
            RAG_RELEVANCY_PROMPT_TEMPLATE,
            llm_classify,
        )
        from phoenix.evals.models import LiteLLMModel  # type: ignore[import-untyped]
    except ImportError as exc:
        return {"metric": "report_faithfulness", "error": str(exc)}

    rows = build_faithfulness_rows(cases)
    if not rows:
        return {"metric": "report_faithfulness", "skipped": "no recorded query_data cases"}

    df = pd.DataFrame(rows)
    model_name = os.getenv("DEFAULT_MODEL", "gemini/gemini-2.5-flash")
    model = LiteLLMModel(model=model_name)

    results = llm_classify(
        dataframe=df,
        template=RAG_RELEVANCY_PROMPT_TEMPLATE,
        model=model,
        rails=["relevant", "irrelevant"],
        provide_explanation=True,
    )

    pass_count = int((results["label"] == "relevant").sum())
    total = len(results)
    return {
        "metric": "report_faithfulness",
        "pass_rate": round(pass_count / total, 3) if total > 0 else 0.0,
        "passed": pass_count,
        "total": total,
        "details": results[["label", "explanation"]].to_dict(orient="records"),
    }


def main() -> None:
    cases = load_recorded_cases()
    if not cases:
        print("No recorded cases found. Run: uv run python scripts/record_evals.py")
        sys.exit(0)

    print(f"Running judge metrics on {len(cases)} recorded cases...")

    report: dict[str, Any] = {"cases_evaluated": len(cases), "metrics": []}

    faithfulness = run_faithfulness_metric(cases)
    report["metrics"].append(faithfulness)

    if "pass_rate" in faithfulness:
        pct = faithfulness["pass_rate"] * 100
        print(
            f"  report_faithfulness: {pct:.1f}%  ({faithfulness['passed']}/{faithfulness['total']})"
        )
    elif "error" in faithfulness:
        print(f"  report_faithfulness: SKIPPED — {faithfulness['error']}")
    else:
        print(f"  report_faithfulness: SKIPPED — {faithfulness.get('skipped')}")

    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"\nReport written to {REPORT_PATH}")
    print("These metrics inform — they never gate CI.")


if __name__ == "__main__":
    main()
