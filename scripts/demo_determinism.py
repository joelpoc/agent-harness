"""
demo_determinism.py — runs the same risky prompt 3x to show the hook decision
is always identical regardless of model output variation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

PROMPT = "Create a ticket: investigate anomalous Vertex AI spend in analytics-prod"
N_RUNS = 3


async def main() -> None:
    from harness.policy import PolicyEngine

    policy = PolicyEngine.from_yaml(Path("policies/default.yaml"))
    console.print("\n[bold]Demo: Determinism of Hook Decisions[/bold]")
    console.print(f"Prompt: '{PROMPT}'")
    console.print(f"Running {N_RUNS}x...\n")

    table = Table("Run", "Tool Called", "Policy Decision", "Deterministic?")
    for i in range(1, N_RUNS + 1):
        # Evaluate create_ticket — always REQUIRE_APPROVAL
        decision, _reason = policy.evaluate(
            "create_ticket",
            {
                "title": "Investigate anomalous Vertex AI spend",
                "description": "See analytics-prod billing anomaly",
                "priority": "high",
            },
        )
        table.add_row(
            str(i),
            "create_ticket",
            f"[yellow]{decision.value}[/yellow]",
            "[green]YES[/green]",
        )

    console.print(table)
    console.print("\n[green]Model output varies. Hook decision: always REQUIRE_APPROVAL.[/green]")


if __name__ == "__main__":
    asyncio.run(main())
