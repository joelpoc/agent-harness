"""Unit tests for the audit logger."""

from __future__ import annotations

from pathlib import Path

from harness.audit import AuditEvent, AuditLogger


def test_record_and_read(tmp_path: Path) -> None:
    logger = AuditLogger(path=tmp_path / "audit.jsonl")
    event = AuditEvent(
        session_id="test-001",
        tool_name="echo",
        args_hash="abc123",
        decision="ALLOW",
        outcome="ok",
    )
    logger.record(event)
    tail = logger.tail(10)
    assert len(tail) == 1
    assert tail[0].tool_name == "echo"
    assert tail[0].session_id == "test-001"


def test_multiple_events_appended(tmp_path: Path) -> None:
    logger = AuditLogger(path=tmp_path / "audit.jsonl")
    for i in range(5):
        logger.record(
            AuditEvent(
                session_id=f"s{i}",
                tool_name="echo",
                args_hash="x",
                decision="ALLOW",
                outcome="ok",
            )
        )
    assert len(logger.tail(10)) == 5


def test_tail_limits_results(tmp_path: Path) -> None:
    logger = AuditLogger(path=tmp_path / "audit.jsonl")
    for i in range(10):
        logger.record(
            AuditEvent(
                session_id=f"s{i}",
                tool_name="echo",
                args_hash="x",
                decision="ALLOW",
                outcome="ok",
            )
        )
    tail = logger.tail(3)
    assert len(tail) == 3


def test_empty_log_returns_empty(tmp_path: Path) -> None:
    logger = AuditLogger(path=tmp_path / "audit.jsonl")
    assert logger.tail() == []
