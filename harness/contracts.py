"""
contracts — Pydantic v2 tool contracts and the central tool registry.

Guarantee: every tool callable by the agent is registered here with a typed
input/output contract. The registry is the single source of truth; the hook
pipeline and policy engine resolve tools by name from this registry.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field


class ToolInput(BaseModel):
    """Base class for all tool input contracts."""

    model_config = {"extra": "forbid"}


class ToolOutput(BaseModel):
    """Base class for all tool output contracts."""

    model_config = {"extra": "forbid"}
    success: bool
    error: str | None = None


class ToolDefinition(BaseModel):
    """Registry entry for a single tool."""

    name: str
    description: str
    input_schema: type[ToolInput]
    output_schema: type[ToolOutput]
    handler: Callable[..., Awaitable[ToolOutput]] = Field(exclude=True)
    source: str = "native"  # "native" | "mcp"
    tags: list[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    def to_litellm_schema(self) -> dict[str, Any]:
        """Return OpenAI-compatible tool schema for LiteLLM."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema.model_json_schema(),
            },
        }


class ToolRegistry:
    """Central registry of all tools available to the agent."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        return self._tools[name]

    def all(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def litellm_schemas(self) -> list[dict[str, Any]]:
        return [t.to_litellm_schema() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())


# Global registry — populated by tool modules at import time
registry = ToolRegistry()
