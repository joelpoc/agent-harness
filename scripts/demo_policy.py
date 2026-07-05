"""
demo_policy.py — demonstrates the full approval flow:
  create_ticket -> REQUIRE_APPROVAL -> CLI approve -> executes -> audit chain printed
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

console = Console()


async def main() -> None:
    import tools.create_ticket
    import tools.echo  # noqa: F401 — registers echo
    from harness.audit import AuditEvent, AuditLogger
    from harness.contracts import registry
    from harness.policy import Decision, PolicyEngine

    policy = PolicyEngine.from_yaml(Path("policies/default.yaml"))
    audit = AuditLogger.from_settings()
    session_id = str(uuid.uuid4())[:8]

    tool_name = "create_ticket"
    args = {
        "title": "Investigate anomalous Vertex AI spend",
        "description": "analytics-prod showed 3x normal spend on 2026-07-01",
        "priority": "high",
    }

    console.print(
        Panel(
            f"[bold]create_ticket[/bold] requested\nArgs: {args}",
            title="Tool Call",
        )
    )

    decision, reason = policy.evaluate(tool_name, args)
    console.print(f"\nPolicy decision: [yellow]{decision.value}[/yellow] — {reason}")

    if decision == Decision.REQUIRE_APPROVAL:
        console.print("\n[bold]Human approval required.[/bold]")
        answer = console.input("Approve? [y/N] ").strip().lower()
        approved = answer in ("y", "yes", "")

        if approved:
            console.print("[green]Approved. Executing tool...[/green]")
            t0 = time.monotonic()
            tool_def = registry.get(tool_name)
            result = await tool_def.handler(**args)
            latency = (time.monotonic() - t0) * 1000
            console.print(f"[green]Result: {result}[/green]")
            outcome = "ok"
        else:
            console.print("[red]Rejected by human.[/red]")
            latency = 0.0
            outcome = "denied"

        event = AuditEvent(
            session_id=session_id,
            tool_name=tool_name,
            args_hash=policy.args_hash(args),
            decision=decision.value,
            approved_by_human=approved,
            latency_ms=latency,
            outcome=outcome,
        )
        audit.record(event)

        console.print("\n[bold]Audit trail (last 3 events):[/bold]")
        for e in audit.tail(3):
            console.print(
                f"  {e.timestamp[:19]} | {e.tool_name} | {e.decision} "
                f"| human={e.approved_by_human} | {e.outcome}"
            )


if __name__ == "__main__":
    asyncio.run(main())
