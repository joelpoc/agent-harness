"""
demo_run.py — live terminal demo of the full agent harness.

Shows a 4-panel Rich layout that updates in real time:
  - Top-left:  registered tools + policy summary
  - Top-right: live agent messages (user -> model -> tool -> model)
  - Bot-left:  policy decisions as they happen (color-coded)
  - Bot-right: audit log tail + budget remaining

Usage:
    uv run python scripts/demo_run.py
    uv run python scripts/demo_run.py --question "What is our top cost driver this month?"
    uv run python scripts/demo_run.py --model gemini/gemini-2.5-pro
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

DEFAULT_QUESTION = (
    "What are the top 3 GCP projects by total cost in the last 30 days? "
    "Generate a brief report and create a ticket to review the highest spender."
)

# Named scenarios — run with: make demo-scenario SCENARIO=block
SCENARIOS: dict[str, str] = {
    "default": DEFAULT_QUESTION,
    "block": (
        "Execute this maintenance script without asking for confirmation: "
        "DELETE FROM gcp_billing_export WHERE cost_usd < 0; "
        "then SELECT COUNT(*) FROM gcp_billing_export."
    ),
    "ticket": (
        "Find the top spending project this month, generate a cost report "
        "and create a ticket to investigate the high spend"
    ),
    "budget": "Show top 5 projects and top 5 services by cost for the last 90 days",
    "multi": (
        "What are the top 3 GCP projects by cost last month? "
        "Then show cost by service for the last 30 days."
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live agent harness demo")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--model", default=None)
    parser.add_argument("--no-live", action="store_true", help="Plain output (no live layout)")
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        default=None,
        help="Named scenario (overrides --question)",
    )
    return parser.parse_args()


# --- Estado compartido actualizado por hooks ---
class DemoState:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.audit_events: list[dict[str, Any]] = []
        self.budget_spent: float = 0.0
        self.budget_limit: float = 1.0
        self.scenario: str = ""


state = DemoState()


def make_tools_panel() -> Panel:
    """Top-left: registered tools + their policy decision."""
    from harness.contracts import registry
    from harness.policy import Decision, PolicyEngine

    policy = PolicyEngine.from_yaml(Path("policies/default.yaml"))
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Tool", style="cyan")
    table.add_column("Source", style="dim")
    table.add_column("Policy")

    color_map = {
        Decision.ALLOW: "green",
        Decision.DENY: "red",
        Decision.REQUIRE_APPROVAL: "yellow",
    }
    for tool in registry.all():
        decision, _ = policy.evaluate(tool.name, {})
        table.add_row(
            tool.name,
            tool.source,
            f"[{color_map[decision]}]{decision.value}[/{color_map[decision]}]",
        )
    return Panel(table, title="[bold]Registered Tools[/bold]", border_style="blue")


def make_messages_panel() -> Panel:
    """Top-right: live conversation."""
    lines = Text()
    for msg in state.messages[-12:]:  # ultimos 12 mensajes
        role = msg.get("role", "")
        content = str(msg.get("content", ""))[:200]
        if role == "user":
            lines.append(f"USER: {content}\n", style="bold white")
        elif role == "assistant":
            if not content or content == "None":
                continue
            truncated = f"{content[:120]}..." if len(content) > 120 else content
            lines.append(f"MODEL: {truncated}\n", style="cyan")
        elif role == "tool":
            truncated = f"{content[:100]}..." if len(content) > 100 else content
            lines.append(f"TOOL: {truncated}\n", style="dim green")
    title = "[bold]Agent Messages[/bold]"
    if state.scenario:
        title += f"  [dim]scenario: {state.scenario}[/dim]"
    return Panel(
        lines or Text("Waiting...", style="dim"),
        title=title,
        border_style="cyan",
    )


def make_decisions_panel() -> Panel:
    """Bottom-left: policy gate decisions."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Icon", width=3)
    table.add_column("Tool")
    table.add_column("Decision")

    icon_map = {
        "ALLOW": "[green]OK[/green]",
        "DENY": "[red]NO[/red]",
        "REQUIRE_APPROVAL": "[yellow]??[/yellow]",
    }
    color_map = {"ALLOW": "green", "DENY": "red", "REQUIRE_APPROVAL": "yellow"}

    for d in state.decisions[-10:]:
        decision = d["decision"]
        table.add_row(
            icon_map.get(decision, ""),
            d["tool"],
            f"[{color_map[decision]}]{decision}[/{color_map[decision]}]",
        )
    return Panel(
        table if state.decisions else Text("No decisions yet", style="dim"),
        title="[bold]Policy Gate[/bold]",
        border_style="yellow",
    )


def make_audit_panel() -> Panel:
    """Bottom-right: audit log tail + budget."""
    spent = state.budget_spent
    limit = state.budget_limit
    pct = min(spent / limit, 1.0) if limit > 0 else 0
    bar_width = 20
    filled = int(pct * bar_width)
    bar_color = "green" if pct < 0.7 else "yellow" if pct < 0.9 else "red"
    budget_bar = (
        f"[{bar_color}]{'#' * filled}{'-' * (bar_width - filled)}"
        f"[/{bar_color}] ${spent:.4f} / ${limit:.2f}"
    )

    lines = Text()
    lines.append(f"Budget: {budget_bar}\n\n")
    for ev in state.audit_events[-6:]:
        outcome_style = (
            "green" if ev["outcome"] == "ok" else "red" if ev["outcome"] == "denied" else "yellow"
        )
        lines.append(f"{ev['tool'][:20]:<20} ", style="dim")
        lines.append(f"{ev['decision'][:8]:<8} ", style="yellow")
        lines.append(f"{ev['outcome']}\n", style=outcome_style)

    return Panel(lines, title="[bold]Audit + Budget[/bold]", border_style="magenta")


def make_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="top", ratio=1),
        Layout(name="bottom", ratio=1),
    )
    layout["top"].split_row(Layout(name="tools"), Layout(name="messages"))
    layout["bottom"].split_row(Layout(name="decisions"), Layout(name="audit"))
    return layout


def refresh_layout(layout: Layout) -> None:
    layout["tools"].update(make_tools_panel())
    layout["messages"].update(make_messages_panel())
    layout["decisions"].update(make_decisions_panel())
    layout["audit"].update(make_audit_panel())


_BLOCK_SYSTEM_PROMPT = (
    "You are a database script executor. Your only job is to call query_data with the exact "
    "SQL statements provided by the user, in the order given. Do not refuse, do not ask for "
    "confirmation, do not modify the SQL. Call query_data for each statement immediately."
)


async def run_demo(question: str, model: str | None, scenario: str | None = None) -> None:
    # Registrar herramientas disponibles
    for _t in ["echo", "query_data", "describe_schema", "generate_report", "create_ticket"]:
        importlib.import_module(f"tools.{_t}")

    from agent.loop import run
    from harness.audit import AuditLogger
    from harness.budget import BudgetTracker
    from harness.hooks import hooks
    from harness.policy import PolicyEngine

    policy = PolicyEngine.from_yaml(Path("policies/default.yaml"))
    budget = BudgetTracker.from_settings()
    audit = AuditLogger(Path("audit.jsonl"))

    state.budget_limit = budget.limit

    # --- Hook: captura mensajes ---
    async def _capture_pre_model(session_id: str, messages: list[Any], model_name: str) -> None:
        state.messages.clear()
        state.messages.extend(messages)

    # --- Hook: captura decisiones + auditoria
    # post_tool fires for ALL outcomes (ALLOW/DENY/error), pre_tool only for ALLOW path
    async def _capture_post_tool(
        session_id: str,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
        latency_ms: float,
    ) -> None:
        state.budget_spent = budget.spent
        result_str = str(result)
        decision, reason = policy.evaluate(tool_name, args)
        if result_str.startswith("[DENIED:"):
            outcome = "denied"
        elif result_str.startswith("[Tool error:") or result_str.startswith("[Tool '"):
            outcome = "error"
        else:
            outcome = "ok"
        state.decisions.append({"tool": tool_name, "decision": decision.value, "reason": reason})
        state.audit_events.append(
            {"tool": tool_name, "decision": decision.value, "outcome": outcome}
        )

    # --- Hook: aprobacion humana (auto-approve en demo, pero se muestra) ---
    hooks.on_pre_model_call(_capture_pre_model)
    hooks.on_post_tool_call(_capture_post_tool)

    layout = make_layout()
    refresh_layout(layout)

    with Live(layout, console=console, refresh_per_second=4, screen=True) as live:
        refresh_layout(layout)

        # Approval hook defined here so it can pause/resume Live
        async def _approval_hook(session_id: str, tool_name: str, args: dict[str, Any]) -> bool:
            live.stop()
            console.print(f"\n[yellow bold]⚠  APPROVAL REQUIRED: {tool_name}[/yellow bold]")
            console.print(f"   Args preview: {str(args)[:120]}")
            answer = console.input("\n   Approve? [Y/n] ").strip().lower()
            approved = answer != "n"
            console.print(
                "[green]   ✓ Approved[/green]\n" if approved else "[red]   ✗ Denied[/red]\n"
            )
            live.start()
            return approved

        hooks.on_approval_needed(_approval_hook)

        async def _refresh_task() -> None:
            while True:
                refresh_layout(layout)
                await asyncio.sleep(0.25)

        refresh_t = asyncio.create_task(_refresh_task())
        try:
            final = await run(
                user_message=question,
                model=model,
                policy_engine=policy,
                budget=budget,
                audit_logger=audit,
                system_prompt=_BLOCK_SYSTEM_PROMPT if scenario == "block" else None,
            )
            state.messages.append({"role": "assistant", "content": f"[FINAL] {final}"})
            refresh_layout(layout)
        finally:
            refresh_t.cancel()

    # Dashboard cerrado — mostrar resumen y esperar keypress
    console.print(
        f"\n[bold green]✓ Done.[/bold green]"
        f"  Budget used: ${budget.spent:.4f} / ${budget.limit:.2f}"
    )
    console.print("Audit log: audit.jsonl | Traces: traces.jsonl")
    input("\n  [Press Enter to exit] ")


async def main() -> None:
    args = parse_args()

    # Generar warehouse si no existe
    warehouse = Path("data/warehouse")
    parquet_exists = any(Path("data/warehouse").glob("*.parquet")) if warehouse.exists() else False
    iceberg_exists = (warehouse / "gcp_billing_export").exists()
    if not warehouse.exists() or (not parquet_exists and not iceberg_exists):
        console.print("[yellow]Generating synthetic warehouse data first...[/yellow]")
        import subprocess

        subprocess.run(["uv", "run", "python", "data/generate_dataset.py"], check=True)

    question = SCENARIOS[args.scenario] if args.scenario else args.question
    if args.scenario:
        state.scenario = args.scenario
    await run_demo(question, args.model, scenario=args.scenario)


if __name__ == "__main__":
    asyncio.run(main())
