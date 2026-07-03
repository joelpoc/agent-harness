"""
Eval runner — executes golden cases against RECORDED model responses.

CI runs these against recorded responses, never live API calls.
Judge metrics (DeepEval) are in a separate non-blocking job.
"""

from __future__ import annotations

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


@pytest.fixture(scope="module")
def policy() -> PolicyEngine:
    return PolicyEngine.from_yaml(POLICY_PATH)


@pytest.mark.parametrize("case", load_cases(), ids=[str(c["id"]) for c in load_cases()])
def test_policy_decisions(case: dict[str, object], policy: PolicyEngine) -> None:
    """Verify that the policy engine produces expected decisions for each case."""
    expected = case.get("expected_policy_decisions", {})
    assert isinstance(expected, dict)
    for tool_name, expected_decision in expected.items():
        # Use empty args for policy-only eval; adversarial SQL tested separately
        args: dict[str, object] = {}
        if tool_name == "query_data" and case.get("adversarial"):
            # Simulate destructive SQL in args
            args = {"sql": "DELETE FROM gcp_billing_export WHERE cost_usd > 0"}

        decision, reason = policy.evaluate(str(tool_name), args)
        assert decision.value == expected_decision, (
            f"Case {case['id']}: {tool_name} -> expected {expected_decision}, "
            f"got {decision.value} ({reason})"
        )
