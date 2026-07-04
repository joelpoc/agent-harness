"""Unit tests for AST-based SQL guard."""

from __future__ import annotations

import pytest

from harness.sql_guard import is_read_only

# --- Safe queries ---


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM gcp_billing_export",
        "SELECT date, SUM(cost_usd) FROM gcp_billing_export GROUP BY date",
        "SELECT * FROM gcp_billing_export WHERE project_id = 'analytics-prod'",
        "WITH cte AS (SELECT * FROM gcp_credits) SELECT * FROM cte",
        "SELECT 1",
    ],
)
def test_read_only_queries_allowed(sql: str) -> None:
    assert is_read_only(sql) is True, f"Should be allowed: {sql}"


# --- Mutating statements ---


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE gcp_billing_export",
        "DELETE FROM gcp_billing_export",
        "INSERT INTO gcp_billing_export VALUES (1)",
        "UPDATE gcp_billing_export SET cost_usd = 0",
        "TRUNCATE TABLE gcp_billing_export",  # maps to exp.TruncateTable
        "ALTER TABLE gcp_billing_export ADD COLUMN foo INT",  # maps to exp.Alter
        "CREATE TABLE foo AS SELECT 1",
    ],
)
def test_mutating_statements_denied(sql: str) -> None:
    assert is_read_only(sql) is False, f"Should be denied: {sql}"


# --- Bypass attempts that substring matching would miss ---


def test_newline_before_table_keyword() -> None:
    """Newline between DROP and TABLE bypasses 'DROP ' substring check."""
    assert is_read_only("DROP\nTABLE gcp_billing_export") is False


def test_multi_statement_batch() -> None:
    """SELECT followed by DROP in the same batch must be denied."""
    assert is_read_only("SELECT 1; DROP TABLE gcp_billing_export") is False


def test_comment_injection() -> None:
    """Comments between keywords bypass naive substring matching."""
    assert is_read_only("DROP/*comment*/TABLE gcp_billing_export") is False


def test_identifier_named_drop_is_allowed() -> None:
    """A table named DROP_SHADOW is NOT a DROP statement."""
    assert is_read_only("SELECT * FROM DROP_SHADOW") is True


def test_unparseable_sql_denied() -> None:
    assert is_read_only("NOT VALID SQL !!!@@@") is False


def test_empty_sql_denied() -> None:
    assert is_read_only("") is False
    assert is_read_only("   ") is False


# --- Policy integration ---


def test_policy_uses_ast_guard_for_query_data() -> None:
    """Policy engine must use AST guard, not substring, for query_data."""
    from pathlib import Path

    from harness.policy import Decision, PolicyEngine

    engine = PolicyEngine.from_yaml(Path("policies/default.yaml"))

    # Newline bypass — would fool substring "DROP " check, must not fool AST
    decision, reason = engine.evaluate("query_data", {"sql": "DROP\nTABLE foo"})
    assert decision == Decision.DENY
    assert "AST" in reason

    # Safe query still allowed
    decision, _ = engine.evaluate("query_data", {"sql": "SELECT * FROM gcp_billing_export"})
    assert decision == Decision.ALLOW
