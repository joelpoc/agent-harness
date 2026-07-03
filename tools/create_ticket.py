"""
create_ticket — creates an operations ticket.

Classified as HIGH RISK in policy (REQUIRE_APPROVAL). This is the demo tool
for showing the human-in-the-loop approval flow.
"""

from __future__ import annotations

from pydantic import Field

from harness.contracts import ToolDefinition, ToolInput, ToolOutput, registry


class CreateTicketInput(ToolInput):
    title: str = Field(description="Ticket title")
    description: str = Field(description="Ticket description")
    priority: str = Field(default="medium", description="Priority: low | medium | high | critical")
    assignee: str | None = Field(default=None, description="Assignee email or username")


class CreateTicketOutput(ToolOutput):
    ticket_id: str = ""
    url: str = ""


_ticket_counter = 0


async def _create_ticket_handler(
    title: str,
    description: str,
    priority: str = "medium",
    assignee: str | None = None,
) -> CreateTicketOutput:
    global _ticket_counter
    _ticket_counter += 1
    ticket_id = f"OPS-{_ticket_counter:04d}"
    return CreateTicketOutput(
        success=True,
        ticket_id=ticket_id,
        url=f"https://tickets.internal/{ticket_id}",
    )


registry.register(
    ToolDefinition(
        name="create_ticket",
        description=(
            "Create an operations ticket. REQUIRES human approval before execution. "
            "Use only when the user explicitly requests ticket creation."
        ),
        input_schema=CreateTicketInput,
        output_schema=CreateTicketOutput,
        handler=_create_ticket_handler,  # type: ignore[arg-type]
        tags=["ops", "high-risk"],
    )
)
