"""
chat.py — interactive REPL for live demos.

Type questions directly; the agent responds in the terminal.
Approval prompts appear inline — type y/n and press Enter.
Ctrl+C or 'exit' to quit.

Usage:
    uv run python scripts/chat.py
    uv run python scripts/chat.py --model ollama/qwen2.5:7b
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
from pathlib import Path

from rich.console import Console
from rich.rule import Rule

# Load all tools into the registry
for _mod in [
    "tools.echo",
    "tools.describe_schema",
    "tools.query_data",
    "tools.generate_report",
    "tools.create_ticket",
]:
    importlib.import_module(_mod)

from agent.loop import run  # noqa: E402
from agent.models import settings as model_settings  # noqa: E402
from harness.audit import AuditLogger  # noqa: E402
from harness.budget import BudgetTracker  # noqa: E402
from harness.hooks import hooks  # noqa: E402
from harness.policy import PolicyEngine  # noqa: E402

console = Console()
policy = PolicyEngine.from_yaml(Path("policies/default.yaml"))


def _register_approval_hook() -> None:
    async def approval_hook(session_id: str, tool_name: str, args: dict) -> bool:  # type: ignore[type-arg]
        console.print(
            f"\n[bold yellow]⚠  APPROVAL REQUIRED:[/bold yellow] [cyan]{tool_name}[/cyan]"
        )
        for k, v in args.items():
            console.print(f"   [dim]{k}:[/dim] {str(v)[:120]}")
        answer = console.input("\n   [bold]Approve?[/bold] [Y/n] ").strip().lower()
        approved = answer in ("y", "yes", "")
        if approved:
            console.print("[green]   ✓ Approved[/green]\n")
        else:
            console.print("[red]   ✗ Denied[/red]\n")
        return approved

    hooks.register_approval_needed(approval_hook)


async def chat(model: str) -> None:
    _register_approval_hook()
    budget = BudgetTracker.from_settings()
    audit = AuditLogger.from_settings()

    console.print(
        Rule(f"[bold cyan]agent-harness chat[/bold cyan] · model: [yellow]{model}[/yellow]")
    )
    console.print("[dim]Type your question. 'exit' to quit.[/dim]\n")

    while True:
        try:
            question = console.input("[bold green]you>[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye.[/dim]")
            break

        if not question or question.lower() in ("exit", "quit"):
            console.print("[dim]Bye.[/dim]")
            break

        console.print()
        with console.status("[dim]thinking…[/dim]", spinner="dots"):
            answer = await run(
                question,
                model=model,
                policy_engine=policy,
                budget=budget,
                audit_logger=audit,
            )

        console.print(f"[bold blue]agent>[/bold blue] {answer}\n")
        console.print(f"[dim]budget used: ${budget.spent:.4f} / ${budget.limit:.2f}[/dim]")
        console.print(Rule(style="dim"))
        console.print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive agent chat")
    parser.add_argument("--model", default=model_settings.default_model)
    args = parser.parse_args()
    asyncio.run(chat(args.model))


if __name__ == "__main__":
    main()
