"""Unit tests for the hook chain — ordering and execution guarantees."""

from __future__ import annotations

from typing import Any

import pytest

from harness.hooks import HookChain


@pytest.mark.asyncio
async def test_pre_model_call_fires_in_order() -> None:
    chain = HookChain()
    order: list[int] = []

    async def hook_a(sid: str, msgs: list[Any], model: str) -> None:
        order.append(1)

    async def hook_b(sid: str, msgs: list[Any], model: str) -> None:
        order.append(2)

    chain.on_pre_model_call(hook_a)
    chain.on_pre_model_call(hook_b)
    await chain.fire_pre_model_call("s1", [], "model")
    assert order == [1, 2]


@pytest.mark.asyncio
async def test_pre_tool_call_raises_halts() -> None:
    chain = HookChain()

    async def blocking_hook(sid: str, tool: str, args: dict[str, Any]) -> None:
        raise PermissionError("blocked by policy")

    chain.on_pre_tool_call(blocking_hook)
    with pytest.raises(PermissionError, match="blocked by policy"):
        await chain.fire_pre_tool_call("s1", "create_ticket", {})


@pytest.mark.asyncio
async def test_post_tool_call_fires() -> None:
    chain = HookChain()
    called_with: list[str] = []

    async def post_hook(
        sid: str, tool: str, args: dict[str, Any], result: Any, latency: float
    ) -> None:
        called_with.append(tool)

    chain.on_post_tool_call(post_hook)
    await chain.fire_post_tool_call("s1", "echo", {}, "result", 12.5)
    assert called_with == ["echo"]


@pytest.mark.asyncio
async def test_approval_hook_returns_true_by_default() -> None:
    chain = HookChain()
    result = await chain.fire_approval_needed("s1", "create_ticket", {})
    assert result is True


@pytest.mark.asyncio
async def test_approval_hook_returns_false_when_rejected() -> None:
    chain = HookChain()

    async def reject_hook(sid: str, tool: str, args: dict[str, Any]) -> bool:
        return False

    chain.on_approval_needed(reject_hook)
    result = await chain.fire_approval_needed("s1", "create_ticket", {})
    assert result is False
