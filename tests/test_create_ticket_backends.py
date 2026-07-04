"""
Unit tests for create_ticket backend dispatch.

The github path is tested via monkeypatched transport — no live network,
no github-mcp-server binary required in CI.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import tools.create_ticket as ct_module
from tools.create_ticket import _create_ticket_handler


@pytest.mark.asyncio
async def test_mock_backend_returns_ops_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TICKETS_BACKEND", "mock")
    result = await _create_ticket_handler(title="Disk alert", description="90% full")
    assert result.success is True
    assert result.ticket_id.startswith("OPS-")
    assert "tickets.internal" in result.url


@pytest.mark.asyncio
async def test_github_backend_calls_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TICKETS_BACKEND", "github")
    mock_call = AsyncMock(return_value=("42", "https://github.com/joel/agent-harness/issues/42"))
    monkeypatch.setattr(ct_module, "_call_github_mcp_create_issue", mock_call)

    result = await _create_ticket_handler(
        title="High disk usage on analytics-prod",
        description="Disk usage exceeded 90% threshold.",
        priority="high",
    )

    assert result.success is True
    assert result.ticket_id == "GH-42"
    assert result.url == "https://github.com/joel/agent-harness/issues/42"
    mock_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_mock_backend_does_not_call_github(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TICKETS_BACKEND", "mock")
    mock_call = AsyncMock()
    monkeypatch.setattr(ct_module, "_call_github_mcp_create_issue", mock_call)

    result = await _create_ticket_handler(title="Test", description="Test")

    assert result.success is True
    assert result.ticket_id.startswith("OPS-")
    mock_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_github_audit_shape_matches_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both backends return the same output contract — audit shape is identical."""
    monkeypatch.setenv("TICKETS_BACKEND", "github")
    monkeypatch.setattr(
        ct_module,
        "_call_github_mcp_create_issue",
        AsyncMock(return_value=("1", "https://github.com/x/y/issues/1")),
    )

    result = await _create_ticket_handler(title="T", description="D")

    assert result.success is True
    assert result.ticket_id != ""
    assert result.url != ""
    assert result.error is None


@pytest.mark.asyncio
async def test_github_body_includes_priority_and_assignee(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TICKETS_BACKEND", "github")
    mock_call = AsyncMock(return_value=("7", "https://github.com/x/y/issues/7"))
    monkeypatch.setattr(ct_module, "_call_github_mcp_create_issue", mock_call)

    await _create_ticket_handler(
        title="CPU spike",
        description="CPU hit 100%",
        priority="critical",
        assignee="ops-team",
    )

    _, body = mock_call.call_args.args
    assert "critical" in body
    assert "ops-team" in body
