"""
Eval runner — executes golden cases against RECORDED model responses.

CI runs these against recorded responses, never live API calls.
Judge metrics (DeepEval) are in a separate non-blocking job.

Three test functions:
  test_policy_decisions   — deterministic; runs always (no recorded response needed)
  test_tool_call_ordering — runs only if recorded_response is populated
  test_sql_pattern        — runs only if recorded_response + expected_sql_pattern present
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from harness.policy import PolicyEngine

CASES_DIR = Path(__file__).parent / "cases"
POLICY_PATH = Path(__file__).parent.parent / "policies" / "default.yaml"


def load_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for f in sorted(CASES_DIR.glob("*.yaml")):
        cases.append(yaml.safe_load(f.read_text()))
    return cases


def load_cases_with_recorded() -> list[dict[str, object]]:
    return [c for c in load_cases() if c.get("recorded_response") is not None]


ALL_CASES = load_cases()
RECORDED_CASES = load_cases_with_recorded()


@pytest.fixture(scope="module")
def policy() -> PolicyEngine:
    return PolicyEngine.from_yaml(POLICY_PATH)


# ---------------------------------------------------------------------------
# Test 1: Policy decisions — always runs, no model needed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", ALL_CASES, ids=[str(c["id"]) for c in ALL_CASES])
def test_policy_decisions(case: dict[str, object], policy: PolicyEngine) -> None:
    """Verify policy engine produces expected decisions. Deterministic — no model."""
    expected = case.get("expected_policy_decisions", {})
    assert isinstance(expected, dict)
    for tool_name, expected_decision in expected.items():
        args: dict[str, object] = {}

        # Use adversarial_args if present (maps tool_name → args dict)
        adversarial_args = case.get("adversarial_args", {})
        assert isinstance(adversarial_args, dict)
        if str(tool_name) in adversarial_args:
            args = dict(adversarial_args[str(tool_name)])
        elif tool_name == "query_data" and case.get("adversarial"):
            # Legacy: cases without adversarial_args but marked adversarial
            args = {"sql": "DELETE FROM gcp_billing_export WHERE cost_usd > 0"}

        decision, reason = policy.evaluate(str(tool_name), args)
        assert decision.value == expected_decision, (
            f"Case {case['id']}: {tool_name} -> expected {expected_decision}, "
            f"got {decision.value} ({reason})"
        )


# ---------------------------------------------------------------------------
# Test 2: Tool-call ordering — only runs against recorded responses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [c for c in RECORDED_CASES if c.get("expected_tool_calls")],
    ids=[str(c["id"]) for c in RECORDED_CASES if c.get("expected_tool_calls")],
)
def test_tool_call_ordering(case: dict[str, object]) -> None:
    """
    Verify the recorded model response called tools in the expected order.
    Skipped automatically if no recorded_response is present.
    """
    recorded = case["recorded_response"]
    assert isinstance(recorded, dict), "recorded_response must be a dict"

    actual_calls: list[str] = [str(tc["tool"]) for tc in recorded.get("tool_calls", [])]
    expected_calls: list[dict[str, object]] = list(
        case.get("expected_tool_calls", [])  # type: ignore[arg-type]
    )

    for i, expected_call in enumerate(expected_calls):
        expected_tool = str(expected_call["tool"])
        assert i < len(actual_calls), (
            f"Case {case['id']}: expected tool #{i + 1} '{expected_tool}' "
            f"but only {len(actual_calls)} tool calls were recorded"
        )
        assert actual_calls[i] == expected_tool, (
            f"Case {case['id']}: tool call #{i + 1} — "
            f"expected '{expected_tool}', got '{actual_calls[i]}'"
        )


# ---------------------------------------------------------------------------
# Test 3: SQL pattern — only runs when recorded response + pattern present
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [c for c in RECORDED_CASES if c.get("expected_sql_pattern")],
    ids=[str(c["id"]) for c in RECORDED_CASES if c.get("expected_sql_pattern")],
)
def test_sql_pattern(case: dict[str, object]) -> None:
    """
    Verify the SQL passed to query_data matches the expected pattern.
    Ensures the model generates semantically correct queries (aggregation, filters, etc.).
    Skipped automatically if no recorded_response is present.
    """
    recorded = case["recorded_response"]
    assert isinstance(recorded, dict)

    pattern = str(case["expected_sql_pattern"])
    sql_calls = [
        str(tc.get("args", {}).get("sql", ""))
        for tc in recorded.get("tool_calls", [])
        if tc.get("tool") == "query_data"
    ]

    assert sql_calls, f"Case {case['id']}: no query_data call found in recorded response"

    matched = any(re.search(pattern, sql, re.IGNORECASE) for sql in sql_calls)
    assert matched, (
        f"Case {case['id']}: no SQL matched pattern '{pattern}'.\nActual SQL calls: {sql_calls}"
    )
