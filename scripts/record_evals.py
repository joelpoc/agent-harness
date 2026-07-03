"""
record_evals.py — runs eval cases against the live model and records responses.

Usage:
    uv run python scripts/record_evals.py [--case 001] [--model anthropic/claude-sonnet-4-5]

Reads cases from evals/cases/*.yaml, runs each non-adversarial case through
the agent loop, and writes the recorded tool calls + final answer back into
the YAML file under `recorded_response`. Existing recordings are overwritten.

Run this once before a demo or when prompts change. CI then runs test_evals.py
against the frozen recordings — no live API calls in CI.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

console = Console()

CASES_DIR = Path(__file__).parent.parent / "evals" / "cases"
POLICY_PATH = Path(__file__).parent.parent / "policies" / "default.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record eval responses")
    parser.add_argument("--case", help="Run only this case ID prefix (e.g. '001')")
    parser.add_argument(
        "--model",
        default=None,
        help="Model override (default: DEFAULT_MODEL env var)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing recordings",
    )
    return parser.parse_args()


async def record_case(
    case_path: Path,
    case: dict[str, Any],
    model: str | None,
    force: bool,
) -> bool:
    """Run a single case through the agent loop and record the response."""
    if case.get("adversarial"):
        console.print(f"  [dim]Skipping adversarial case {case['id']}[/dim]")
        return False

    if case.get("recorded_response") is not None and not force:
        console.print(f"  [dim]Already recorded {case['id']} (use --force to overwrite)[/dim]")
        return False

    # Import tool modules so they register themselves in the global registry
    import importlib

    for _tool in ["echo", "query_data", "describe_schema", "generate_report", "create_ticket"]:
        importlib.import_module(f"tools.{_tool}")

    from agent.loop import run
    from harness.audit import AuditLogger
    from harness.budget import BudgetTracker
    from harness.hooks import hooks
    from harness.policy import PolicyEngine

    # Intercept tool calls to record them
    recorded_tool_calls: list[dict[str, Any]] = []

    async def _record_post_hook(
        session_id: str,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
        latency_ms: float,
    ) -> None:
        recorded_tool_calls.append({"tool": tool_name, "args": args})

    # Register recording hook temporarily
    hooks._post_tool.append(_record_post_hook)

    try:
        policy = PolicyEngine.from_yaml(POLICY_PATH)
        # Use generous budget for recording
        budget = BudgetTracker(limit_usd=5.0)
        # Null audit logger (don't pollute audit log during recording)
        audit = AuditLogger(path=Path("/tmp/record_evals_audit.jsonl"))

        # Auto-approve all approvals during recording
        async def _auto_approve(session_id: str, tool: str, args: dict[str, Any]) -> bool:
            console.print(f"    [yellow]Auto-approving {tool} for recording[/yellow]")
            return True

        hooks._on_approval.append(_auto_approve)

        try:
            final_answer = await run(
                user_message=str(case["user_message"]),
                model=model,
                policy_engine=policy,
                budget=budget,
                audit_logger=audit,
            )
        finally:
            hooks._on_approval.remove(_auto_approve)

    finally:
        hooks._post_tool.remove(_record_post_hook)

    # Write recording back to YAML
    case["recorded_response"] = {
        "tool_calls": recorded_tool_calls,
        "final_answer": final_answer,
        "model": model,
    }

    case_path.write_text(yaml.dump(case, default_flow_style=False, allow_unicode=True))
    console.print(f"  [green]Recorded {case['id']}: {len(recorded_tool_calls)} tool calls[/green]")
    return True


async def main() -> None:
    args = parse_args()

    case_files = sorted(CASES_DIR.glob("*.yaml"))
    if args.case:
        case_files = [f for f in case_files if f.name.startswith(args.case)]

    if not case_files:
        console.print("[red]No matching cases found.[/red]")
        return

    console.print(f"\n[bold]Recording {len(case_files)} eval case(s)...[/bold]")
    console.print(f"Model: {args.model or '(DEFAULT_MODEL env var)'}\n")

    recorded = 0
    for case_path in case_files:
        case: dict[str, Any] = yaml.safe_load(case_path.read_text())
        console.print(f"[bold]{case['id']}[/bold] — {case.get('description', '')}")
        ok = await record_case(case_path, case, args.model, args.force)
        if ok:
            recorded += 1

    console.print(f"\n[green]Done. {recorded} case(s) recorded.[/green]")
    console.print("Run [bold]uv run pytest evals/[/bold] to validate.")


if __name__ == "__main__":
    asyncio.run(main())
