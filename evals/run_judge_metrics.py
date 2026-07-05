"""
run_judge_metrics.py — LLM-as-judge metrics via Arize Phoenix Evals.

Two execution modes (auto-detected):
  1. OFFLINE  — reads from golden YAML cases (recorded_response)
               runs always, no Phoenix server needed
  2. LIVE     — pulls tool_call spans from a running Phoenix instance,
               judges them, and pushes annotations back so scores appear
               visually in the Phoenix UI (localhost:6006/evaluators)

Usage:
  make evals-judge            # offline (golden cases)
  PHOENIX_ENABLED=true make evals-judge   # live (Phoenix must be running)

Judge model: gemini/gemini-2.5-pro (more capable than the agent's flash model —
the judge should be smarter than what it evaluates).
Never runs in CI as a blocking gate — informative only.
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

# Use a more capable model for judging than the agent uses
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini/gemini-2.5-pro")

FAITHFULNESS_TEMPLATE = """
You are evaluating whether an AI data-analysis assistant's answer is grounded
in SQL queries rather than invented. The assistant must derive all numbers from
query_data tool calls — it must never guess or estimate figures.

[User question]
{question}

[SQL queries that were executed to answer the question]
{reference}

[Assistant's final answer]
{output}

The core guarantee: the assistant must call query_data and use the results —
it must never invent numbers.

Does the assistant's answer appear to be derived from SQL queries like the ones
above (i.e. the numbers are the kind such queries would return), or does the
answer appear to be invented without querying?

Answer with exactly one word:
- "faithful"      — answer is consistent with having run the SQL queries
- "hallucinated"  — figures appear invented or inconsistent with the queries
""".strip()

SQL_RELEVANCE_TEMPLATE = """
You are evaluating whether a SQL query correctly addresses a user's question
about GCP cloud billing data.

[User question]
{question}

[Generated SQL]
{sql}

Does this SQL query retrieve the data needed to answer the question?
Consider: correct aggregation, correct filters (time range, dimensions), and
whether the query structure matches what the question asks for.

Answer with exactly one word: "relevant" or "irrelevant".
""".strip()


# ---------------------------------------------------------------------------
# Data builders — offline (golden YAML cases)
# ---------------------------------------------------------------------------


def load_recorded_cases() -> list[dict[str, Any]]:
    cases = []
    for f in sorted(CASES_DIR.glob("*.yaml")):
        case: dict[str, Any] = yaml.safe_load(f.read_text())
        if case.get("recorded_response") and not case.get("adversarial"):
            cases.append(case)
    return cases


def build_faithfulness_df_offline(cases: list[dict[str, Any]]) -> Any:
    import pandas as pd

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
    return pd.DataFrame(rows)


def build_sql_relevance_df_offline(cases: list[dict[str, Any]]) -> Any:
    import pandas as pd

    rows = []
    for case in cases:
        recorded = case["recorded_response"]
        tool_calls = recorded.get("tool_calls", [])
        # Skip MAX(date) pre-flight queries — use the last substantive one
        sql_calls = [
            str(tc.get("args", {}).get("sql", ""))
            for tc in tool_calls
            if tc.get("tool") == "query_data" and tc.get("args", {}).get("sql")
        ]
        if not sql_calls:
            continue
        # Join all SQL calls — judge evaluates the full set of queries collectively
        combined_sql = "\n\n-- next query --\n\n".join(sql_calls)
        rows.append(
            {
                "id": case["id"],
                "question": str(case["user_message"]),
                "sql": combined_sql,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Data builders — live (from Phoenix spans)
# ---------------------------------------------------------------------------


def build_faithfulness_df_live(phoenix_url: str) -> Any:
    """Pull model_call spans from Phoenix and build faithfulness eval rows."""
    import pandas as pd
    from phoenix.client import Client
    from phoenix.client.types.spans import SpanQuery

    client = Client(base_url=phoenix_url)

    # Pull model_call spans that have both input and output
    query = (
        SpanQuery()
        .select("context.span_id", "attributes.input.value", "attributes.output.value")
        .where("name == 'model_call'")
    )
    try:
        df = client.spans.get_spans_dataframe(query=query, limit=50)
    except Exception as exc:
        print(f"  [warn] could not pull spans from Phoenix: {exc}")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    rows = []
    for _, row in df.iterrows():
        input_val = row.get("attributes.input.value") or row.get("input.value", "")
        output_val = row.get("attributes.output.value") or row.get("output.value", "")
        if input_val and output_val:
            rows.append(
                {
                    "span_id": str(row.get("context.span_id", "")),
                    "question": str(input_val)[:500],
                    "reference": "",  # not available from model_call spans directly
                    "output": str(output_val)[:1000],
                }
            )
    return pd.DataFrame(rows)


def build_sql_relevance_df_live(phoenix_url: str) -> Any:
    """Pull query_data tool_call spans from Phoenix and build SQL relevance rows."""
    import pandas as pd
    from phoenix.client import Client
    from phoenix.client.types.spans import SpanQuery

    client = Client(base_url=phoenix_url)

    query = (
        SpanQuery()
        .select("context.span_id", "attributes.input.value", "attributes.output.value")
        .where("name == 'tool_call'")
    )
    try:
        df = client.spans.get_spans_dataframe(query=query, limit=100)
    except Exception as exc:
        print(f"  [warn] could not pull spans from Phoenix: {exc}")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    rows = []
    for _, row in df.iterrows():
        input_val = str(row.get("attributes.input.value") or row.get("input.value", ""))
        output_val = str(row.get("attributes.output.value") or row.get("output.value", ""))
        # Only keep query_data tool calls (input contains "query_data")
        if "query_data" not in input_val.lower():
            continue
        rows.append(
            {
                "span_id": str(row.get("context.span_id", "")),
                "question": input_val[:500],
                "sql": output_val[:500],
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Push annotations back to Phoenix (live mode only)
# ---------------------------------------------------------------------------


def push_annotations_to_phoenix(
    phoenix_url: str,
    results_df: Any,
    score_col: str,
    metric_name: str,
    passing_label: str,
) -> int:
    """Push LLM judge scores as span annotations — visible in Phoenix UI."""
    from phoenix.client import Client
    from phoenix.client.resources.spans import SpanAnnotationData

    if "span_id" not in results_df.columns:
        return 0

    client = Client(base_url=phoenix_url)
    annotations: list[SpanAnnotationData] = []

    for _, row in results_df.iterrows():
        span_id = str(row.get("span_id", ""))
        score_obj = row.get(score_col)
        if not span_id or not isinstance(score_obj, dict):
            continue

        label = score_obj.get("label", "")
        explanation = score_obj.get("explanation", "")
        score_val = 1.0 if label == passing_label else 0.0

        annotations.append(
            SpanAnnotationData(
                span_id=span_id,
                name=metric_name,
                annotator_kind="LLM",
                result={
                    "label": label,
                    "score": score_val,
                    "explanation": explanation[:500] if explanation else "",
                },
                metadata={"judge_model": JUDGE_MODEL},
            )
        )

    if not annotations:
        return 0

    try:
        client.spans.log_span_annotations(span_annotations=annotations, sync=True)
        return len(annotations)
    except Exception as exc:
        print(f"  [warn] failed to push annotations to Phoenix: {exc}")
        return 0


# ---------------------------------------------------------------------------
# Core classifier runner
# ---------------------------------------------------------------------------


def _run_classifier_metric(
    metric_name: str,
    df: Any,
    template: str,
    passing_label: str,
    choices: list[str],
    phoenix_url: str | None = None,
) -> dict[str, Any]:
    try:
        from phoenix.evals import LLM, create_classifier, evaluate_dataframe
    except ImportError as exc:
        return {"metric": metric_name, "error": str(exc)}

    if df.empty:
        return {"metric": metric_name, "skipped": "no eligible cases"}

    llm = LLM(provider="litellm", model=JUDGE_MODEL)
    evaluator = create_classifier(
        name=metric_name,
        prompt_template=template,
        llm=llm,
        choices=choices,
    )

    results = evaluate_dataframe(dataframe=df, evaluators=[evaluator], hide_tqdm_bar=True)

    score_col = next((c for c in results.columns if c.endswith("_score")), None)
    if score_col is None:
        return {"metric": metric_name, "error": f"no score column in {list(results.columns)}"}

    labels = results[score_col].apply(lambda s: s.get("label") if isinstance(s, dict) else None)
    pass_count = int((labels == passing_label).sum())
    total = int(labels.notna().sum())

    # Push to Phoenix if running
    pushed = 0
    if phoenix_url and "span_id" in results.columns:
        pushed = push_annotations_to_phoenix(
            phoenix_url, results, score_col, metric_name, passing_label
        )

    details = [
        {
            "id": str(results["id"].iloc[i]) if "id" in results.columns else str(i),
            "label": labels.iloc[i],
            "explanation": (
                results[score_col].iloc[i].get("explanation", "")
                if isinstance(results[score_col].iloc[i], dict)
                else ""
            ),
        }
        for i in range(len(results))
    ]
    result: dict[str, Any] = {
        "metric": metric_name,
        "pass_rate": round(pass_count / total, 3) if total > 0 else 0.0,
        "passed": pass_count,
        "total": total,
        "details": details,
    }
    if pushed:
        result["phoenix_annotations_pushed"] = pushed
    return result


# ---------------------------------------------------------------------------
# Public metric runners
# ---------------------------------------------------------------------------


def run_faithfulness_metric(
    cases: list[dict[str, Any]], phoenix_url: str | None = None
) -> dict[str, Any]:
    """Evaluate whether the final answer is faithful to query_data results."""
    if phoenix_url:
        df = build_faithfulness_df_live(phoenix_url)
    else:
        df = build_faithfulness_df_offline(cases)

    return _run_classifier_metric(
        metric_name="report_faithfulness",
        df=df,
        template=FAITHFULNESS_TEMPLATE,
        passing_label="faithful",
        choices=["faithful", "hallucinated"],
        phoenix_url=phoenix_url,
    )


def run_sql_relevance_metric(
    cases: list[dict[str, Any]], phoenix_url: str | None = None
) -> dict[str, Any]:
    """Evaluate whether the generated SQL addresses the user question."""
    if phoenix_url:
        df = build_sql_relevance_df_live(phoenix_url)
    else:
        df = build_sql_relevance_df_offline(cases)

    return _run_classifier_metric(
        metric_name="sql_relevance",
        df=df,
        template=SQL_RELEVANCE_TEMPLATE,
        passing_label="relevant",
        choices=["relevant", "irrelevant"],
        phoenix_url=phoenix_url,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _phoenix_url() -> str | None:
    """Return Phoenix base URL if Phoenix integration is enabled AND reachable."""
    if os.getenv("PHOENIX_ENABLED", "").lower() not in ("true", "1", "yes"):
        return None
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces")
    # Strip /v1/traces suffix — Client needs the base URL
    base = endpoint.split("/v1/")[0] if "/v1/" in endpoint else endpoint

    # Probe reachability before committing to live mode
    try:
        import urllib.request

        urllib.request.urlopen(f"{base}/health", timeout=2)
        return base
    except Exception:
        return None


def main() -> None:
    cases = load_recorded_cases()
    phoenix_url = _phoenix_url()

    # If PHOENIX_ENABLED but server unreachable, warn and fall back to offline
    if os.getenv("PHOENIX_ENABLED", "").lower() in ("true", "1", "yes") and phoenix_url is None:
        print("⚠  PHOENIX_ENABLED=true but Phoenix is not reachable.")
        print("   Start it first:  make phoenix")
        print("   Falling back to OFFLINE mode (golden cases).\n")

    if not cases:
        print("No recorded cases found. Run: uv run python scripts/record_evals.py")
        sys.exit(0)

    mode = "LIVE (Phoenix)" if phoenix_url else "OFFLINE (golden cases)"
    n = "live" if phoenix_url else len(cases)
    print(f"Running judge metrics — mode: {mode}, cases: {n}")
    print(f"Judge model: {JUDGE_MODEL}")
    if phoenix_url:
        print(f"Phoenix: {phoenix_url}  (annotations will be pushed back)")
    print()

    report: dict[str, Any] = {
        "mode": mode,
        "judge_model": JUDGE_MODEL,
        "cases_evaluated": len(cases),
        "metrics": [],
    }

    for run_metric in (run_faithfulness_metric, run_sql_relevance_metric):
        result = run_metric(cases, phoenix_url)
        report["metrics"].append(result)
        name = result["metric"]
        if "pass_rate" in result:
            pct = result["pass_rate"] * 100
            pushed = result.get("phoenix_annotations_pushed", 0)
            phoenix_note = f"  → {pushed} annotations pushed to Phoenix" if pushed else ""
            print(f"  {name}: {pct:.1f}%  ({result['passed']}/{result['total']}){phoenix_note}")
        elif "error" in result:
            print(f"  {name}: SKIPPED — {result['error']}")
        else:
            print(f"  {name}: SKIPPED — {result.get('skipped')}")

    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"\nReport written to {REPORT_PATH}")
    if phoenix_url:
        print(f"View annotations: {phoenix_url}  (Traces → any span → Annotations tab)")
    print("These metrics inform — they never gate CI.")


if __name__ == "__main__":
    main()
