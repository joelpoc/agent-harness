"""
policy — YAML-driven policy engine for tool calls.

Guarantee: every tool call receives one of three decisions — ALLOW, DENY,
or REQUIRE_APPROVAL — based on a policy file loaded at startup. Unknown tools
are DENIED by default (deny-by-default). Policy decisions are deterministic
given the same input; the model has no influence over them.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class Decision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class ToolPolicy(BaseModel):
    """Policy rule for a single tool or tool pattern."""

    pattern: str  # exact name or glob-style prefix (e.g. "mcp/*")
    decision: Decision
    reason: str = ""
    # Optional: deny if any arg key matches (e.g. deny if "table" == "salaries")
    deny_if: dict[str, list[str]] = Field(default_factory=dict)
    # AST-based SQL guard: deny if the "sql" arg contains any mutating statement
    require_read_only_sql: bool = False


class PolicyConfig(BaseModel):
    default: Decision = Decision.DENY
    tools: list[ToolPolicy] = Field(default_factory=list)


class PolicyEngine:
    """Evaluates tool calls against a loaded YAML policy."""

    def __init__(self, config: PolicyConfig) -> None:
        self._config = config

    @classmethod
    def from_yaml(cls, path: Path) -> PolicyEngine:
        raw = yaml.safe_load(path.read_text())
        config = PolicyConfig.model_validate(raw)
        return cls(config)

    def evaluate(self, tool_name: str, args: dict[str, Any]) -> tuple[Decision, str]:
        """
        Returns (decision, reason).
        Checks rules in order; first match wins. Falls back to default.
        """
        for rule in self._config.tools:
            if self._matches(tool_name, rule.pattern):
                if rule.decision == Decision.ALLOW:
                    # AST-based SQL guard (runs before substring check — stricter)
                    if rule.require_read_only_sql and "sql" in args:
                        from harness.sql_guard import is_read_only

                        if not is_read_only(str(args["sql"])):
                            return Decision.DENY, "SQL contains mutating statement (AST guard)"
                    # Substring deny_if (general-purpose, non-SQL args)
                    for arg_key, forbidden_values in rule.deny_if.items():
                        arg_val = str(args.get(arg_key, ""))
                        if any(fv.lower() in arg_val.lower() for fv in forbidden_values):
                            return Decision.DENY, f"Arg '{arg_key}' matches forbidden value"
                return rule.decision, rule.reason
        return self._config.default, "No matching rule — default policy"

    def _matches(self, tool_name: str, pattern: str) -> bool:
        if pattern.endswith("/*"):
            prefix = pattern[:-2]
            return tool_name.startswith(prefix + "/") or tool_name == prefix
        return tool_name == pattern

    def args_hash(self, args: dict[str, Any]) -> str:
        """Deterministic hash of tool args for audit (never store raw args)."""
        serialised = json.dumps(args, sort_keys=True, default=str)
        return hashlib.sha256(serialised.encode()).hexdigest()[:16]
