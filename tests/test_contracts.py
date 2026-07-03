"""Unit tests for the tool registry and contracts."""

from __future__ import annotations

import pytest

from harness.contracts import ToolDefinition, ToolInput, ToolOutput, ToolRegistry


class PingInput(ToolInput):
    message: str


class PingOutput(ToolOutput):
    echoed: str = ""


async def _ping_handler(message: str) -> PingOutput:
    return PingOutput(success=True, echoed=message)


def make_tool(name: str = "ping") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="test tool",
        input_schema=PingInput,
        output_schema=PingOutput,
        handler=_ping_handler,  # type: ignore[arg-type]
    )


def test_register_and_get() -> None:
    reg = ToolRegistry()
    reg.register(make_tool("ping"))
    tool = reg.get("ping")
    assert tool.name == "ping"


def test_duplicate_registration_raises() -> None:
    reg = ToolRegistry()
    reg.register(make_tool("ping"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(make_tool("ping"))


def test_missing_tool_raises() -> None:
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.get("nonexistent")


def test_litellm_schema_shape() -> None:
    reg = ToolRegistry()
    reg.register(make_tool("ping"))
    schemas = reg.litellm_schemas()
    assert len(schemas) == 1
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "ping"


def test_extra_fields_forbidden() -> None:
    with pytest.raises(Exception):
        PingInput.model_validate({"message": "hi", "extra_field": "bad"})
