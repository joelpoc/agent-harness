"""
hooks — lifecycle hook chain for the agent harness.

Guarantee: every hook registered here executes on every relevant event, in
registration order. Hooks are synchronous checkpoints; a hook may raise to
halt execution. The agent loop calls hooks — hooks never call the agent loop.

Hook types:
  pre_model_call(session_id, messages, model) -> None | raise
  pre_tool_call(session_id, tool_name, args) -> None | raise
  post_tool_call(session_id, tool_name, args, result, latency_ms) -> None
  on_budget_exceeded(session_id, spent, limit) -> None
  on_approval_needed(session_id, tool_name, args) -> bool  (True = approved)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# Hook signatures
PreModelCallHook = Callable[[str, list[dict[str, Any]], str], Awaitable[None]]
PreToolCallHook = Callable[[str, str, dict[str, Any]], Awaitable[None]]
PostToolCallHook = Callable[[str, str, dict[str, Any], Any, float], Awaitable[None]]
OnBudgetExceededHook = Callable[[str, float, float], Awaitable[None]]
OnApprovalNeededHook = Callable[[str, str, dict[str, Any]], Awaitable[bool]]


class HookChain:
    """Ordered registry of lifecycle hooks."""

    def __init__(self) -> None:
        self._pre_model: list[PreModelCallHook] = []
        self._pre_tool: list[PreToolCallHook] = []
        self._post_tool: list[PostToolCallHook] = []
        self._on_budget: list[OnBudgetExceededHook] = []
        self._on_approval: list[OnApprovalNeededHook] = []

    # --- Registration ---

    def on_pre_model_call(self, fn: PreModelCallHook) -> PreModelCallHook:
        self._pre_model.append(fn)
        return fn

    def on_pre_tool_call(self, fn: PreToolCallHook) -> PreToolCallHook:
        self._pre_tool.append(fn)
        return fn

    def on_post_tool_call(self, fn: PostToolCallHook) -> PostToolCallHook:
        self._post_tool.append(fn)
        return fn

    def on_budget_exceeded(self, fn: OnBudgetExceededHook) -> OnBudgetExceededHook:
        self._on_budget.append(fn)
        return fn

    def on_approval_needed(self, fn: OnApprovalNeededHook) -> OnApprovalNeededHook:
        self._on_approval.append(fn)
        return fn

    # --- Execution ---

    async def fire_pre_model_call(
        self, session_id: str, messages: list[dict[str, Any]], model: str
    ) -> None:
        for hook in self._pre_model:
            await hook(session_id, messages, model)

    async def fire_pre_tool_call(
        self, session_id: str, tool_name: str, args: dict[str, Any]
    ) -> None:
        for hook in self._pre_tool:
            await hook(session_id, tool_name, args)

    async def fire_post_tool_call(
        self,
        session_id: str,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
        latency_ms: float,
    ) -> None:
        for hook in self._post_tool:
            await hook(session_id, tool_name, args, result, latency_ms)

    async def fire_budget_exceeded(self, session_id: str, spent: float, limit: float) -> None:
        for hook in self._on_budget:
            await hook(session_id, spent, limit)

    async def fire_approval_needed(
        self, session_id: str, tool_name: str, args: dict[str, Any]
    ) -> bool:
        """Returns True if approved. Last handler wins (or True if no handlers)."""
        approved = True
        for hook in self._on_approval:
            approved = await hook(session_id, tool_name, args)
        return approved


# Global hook chain — populated by the agent runner at startup
hooks = HookChain()
