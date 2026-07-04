"""Unit tests for the policy engine. These prove deterministic guarantees."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.policy import Decision, PolicyConfig, PolicyEngine


def make_engine_from_config(config_dict: dict[str, Any]) -> PolicyEngine:
    config = PolicyConfig.model_validate(config_dict)
    return PolicyEngine(config)


def test_allow_rule() -> None:
    engine = make_engine_from_config(
        {
            "default": "DENY",
            "tools": [{"pattern": "echo", "decision": "ALLOW", "reason": "safe"}],
        }
    )
    decision, _ = engine.evaluate("echo", {})
    assert decision == Decision.ALLOW


def test_deny_by_default() -> None:
    engine = make_engine_from_config({"default": "DENY", "tools": []})
    decision, reason = engine.evaluate("unknown_tool", {})
    assert decision == Decision.DENY
    assert "default" in reason.lower()


def test_require_approval() -> None:
    engine = make_engine_from_config(
        {
            "default": "DENY",
            "tools": [{"pattern": "create_ticket", "decision": "REQUIRE_APPROVAL"}],
        }
    )
    decision, _ = engine.evaluate("create_ticket", {})
    assert decision == Decision.REQUIRE_APPROVAL


def test_deny_if_matches() -> None:
    engine = make_engine_from_config(
        {
            "default": "DENY",
            "tools": [
                {
                    "pattern": "query_data",
                    "decision": "ALLOW",
                    "deny_if": {"sql": ["DROP ", "DELETE "]},
                }
            ],
        }
    )
    decision, _ = engine.evaluate("query_data", {"sql": "DELETE FROM foo"})
    assert decision == Decision.DENY


def test_deny_if_does_not_match_safe_query() -> None:
    engine = make_engine_from_config(
        {
            "default": "DENY",
            "tools": [
                {
                    "pattern": "query_data",
                    "decision": "ALLOW",
                    "deny_if": {"sql": ["DROP ", "DELETE "]},
                }
            ],
        }
    )
    decision, _ = engine.evaluate("query_data", {"sql": "SELECT * FROM billing"})
    assert decision == Decision.ALLOW


def test_mcp_prefix_pattern() -> None:
    engine = make_engine_from_config(
        {
            "default": "DENY",
            "tools": [{"pattern": "mcp/*", "decision": "REQUIRE_APPROVAL"}],
        }
    )
    decision, _ = engine.evaluate("mcp/describe_schema", {})
    assert decision == Decision.REQUIRE_APPROVAL


def test_args_hash_is_deterministic() -> None:
    engine = make_engine_from_config({"default": "DENY", "tools": []})
    args: dict[str, Any] = {"sql": "SELECT 1", "limit": 10}
    h1 = engine.args_hash(args)
    h2 = engine.args_hash(args)
    assert h1 == h2
    assert len(h1) == 16


def test_policy_from_yaml(tmp_path: Path) -> None:
    yaml_content = """
default: DENY
tools:
  - pattern: echo
    decision: ALLOW
    reason: test
"""
    p = tmp_path / "policy.yaml"
    p.write_text(yaml_content)
    engine = PolicyEngine.from_yaml(p)
    decision, _ = engine.evaluate("echo", {})
    assert decision == Decision.ALLOW


# --- GitHub MCP trust boundary ---


def test_github_whitelisted_tool_requires_approval() -> None:
    """create_issues is the ONLY whitelisted GitHub MCP tool — must be REQUIRE_APPROVAL."""
    engine = PolicyEngine.from_yaml(Path("policies/default.yaml"))
    decision, _ = engine.evaluate("mcp/github/create_issues", {})
    assert decision == Decision.REQUIRE_APPROVAL


def test_github_unlisted_tools_are_denied() -> None:
    """Any GitHub MCP tool NOT in the whitelist must be DENY — literal trust boundary."""
    engine = PolicyEngine.from_yaml(Path("policies/default.yaml"))
    unlisted = [
        "mcp/github/list_repositories",
        "mcp/github/get_file_contents",
        "mcp/github/push_files",
        "mcp/github/create_branch",
        "mcp/github/delete_branch",
        "mcp/github/merge_pull_request",
    ]
    for tool in unlisted:
        decision, reason = engine.evaluate(tool, {})
        assert decision == Decision.DENY, f"{tool} should be DENY but got {decision}: {reason}"
