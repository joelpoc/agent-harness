"""
create_ticket — creates an operations ticket.

Classified as HIGH RISK in policy (REQUIRE_APPROVAL). This is the demo tool
for showing the human-in-the-loop approval flow.

Backend is selected by TICKETS_BACKEND env var:
  mock   (default) — offline, no credentials needed
  github           — real GitHub issue via github-mcp-server stdio
"""

from __future__ import annotations

import json
import os

from pydantic import Field

from harness.backends import BackendSettings
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


async def _call_github_mcp_create_issue(title: str, body: str) -> tuple[str, str]:
    """
    Connect to github-mcp-server (stdio) and create a GitHub issue.
    Returns (issue_number, html_url).

    Separated from the handler so tests can monkeypatch this without
    spawning a real process or hitting the GitHub API.
    """
    from mcp import ClientSession, StdioServerParameters  # type: ignore[import-untyped]
    from mcp.client.stdio import stdio_client  # type: ignore[import-untyped]

    settings = BackendSettings()
    env = {**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": settings.github_token}
    server_params = StdioServerParameters(
        command=settings.github_mcp_command,
        args=["stdio"],
        env=env,
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "create_issue",
                {
                    "owner": settings.github_repo_owner,
                    "repo": settings.github_repo_name,
                    "title": title,
                    "body": body,
                },
            )
            content = result.content[0].text if result.content else "{}"
            data = json.loads(content)
            return str(data.get("number", "?")), str(data.get("html_url", ""))


async def _create_ticket_handler(
    title: str,
    description: str,
    priority: str = "medium",
    assignee: str | None = None,
) -> CreateTicketOutput:
    backend = BackendSettings().tickets_backend

    if backend == "github":
        body = f"{description}\n\n*Priority: {priority}*"
        if assignee:
            body += f"\n*Assignee: {assignee}*"
        issue_number, url = await _call_github_mcp_create_issue(title, body)
        return CreateTicketOutput(
            success=True,
            ticket_id=f"GH-{issue_number}",
            url=url,
        )

    # mock backend (default — offline, no credentials)
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
