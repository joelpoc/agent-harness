"""echo — test tool for M1 skeleton validation."""

from __future__ import annotations

from pydantic import Field

from harness.contracts import ToolDefinition, ToolInput, ToolOutput, registry


class EchoInput(ToolInput):
    message: str = Field(description="The message to echo back")


class EchoOutput(ToolOutput):
    echoed: str = ""


async def _echo_handler(message: str) -> EchoOutput:
    return EchoOutput(success=True, echoed=f"[ECHO] {message}")


registry.register(
    ToolDefinition(
        name="echo",
        description="Echo a message back. Used for M1 skeleton validation.",
        input_schema=EchoInput,
        output_schema=EchoOutput,
        handler=_echo_handler,  # type: ignore[arg-type]
        tags=["demo"],
    )
)
