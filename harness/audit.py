"""
audit — immutable JSONL audit trail written by the shell.

Guarantee: every tool call produces exactly one audit event, written by the
shell after the tool completes (or fails). Events are append-only JSONL.
The model does not write to the audit log and cannot alter past events.
Fields: timestamp, session_id, tool_name, args_hash, decision, tokens,
cost_usd, latency_ms, outcome.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuditSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    audit_log_path: Path = Field(default=Path("audit.jsonl"), alias="AUDIT_LOG_PATH")


class AuditEvent(BaseModel):
    """A single immutable audit record."""

    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    session_id: str
    tool_name: str
    args_hash: str  # sha256[:16] of redacted args — never raw args
    decision: str  # ALLOW | DENY | REQUIRE_APPROVAL
    approved_by_human: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    outcome: str = "ok"  # "ok" | "error" | "denied" | "budget_exceeded"
    error: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AuditLogger:
    """Appends AuditEvents to a JSONL file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_settings(cls) -> AuditLogger:
        settings = AuditSettings()
        return cls(path=settings.audit_log_path)

    def record(self, event: AuditEvent) -> None:
        with self._path.open("a") as f:
            f.write(event.model_dump_json() + "\n")

    def tail(self, n: int = 10) -> list[AuditEvent]:
        """Return the last n events (for demo display)."""
        if not self._path.exists():
            return []
        lines = self._path.read_text().strip().splitlines()
        return [AuditEvent.model_validate_json(line) for line in lines[-n:]]
