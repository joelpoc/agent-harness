"""
agent loop — the probabilistic core.

Intentionally thin: calls LiteLLM, dispatches tool calls through the harness
hook pipeline, accumulates messages. No framework. ~80-120 lines.

The loop does not know about policy, budget, or audit — the hook pipeline
handles all of that. The loop's only job is the message/tool-call cycle.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import litellm  # type: ignore[import-untyped]

from agent.models import settings as model_settings
from harness.audit import AuditEvent, AuditLogger
from harness.budget import BudgetExceededError, BudgetTracker
from harness.contracts import registry
from harness.hooks import hooks
from harness.policy import Decision, PolicyEngine
from harness.tracing import Span, tracer

MAX_TURNS = 20


async def run(
    user_message: str,
    model: str | None = None,
    session_id: str | None = None,
    policy_engine: PolicyEngine | None = None,
    budget: BudgetTracker | None = None,
    audit_logger: AuditLogger | None = None,
) -> str:
    """Run the agent loop for a single user message. Returns final text response."""
    model = model or model_settings.default_model
    session_id = session_id or str(uuid.uuid4())[:8]
    budget = budget or BudgetTracker.from_settings()
    audit_logger = audit_logger or AuditLogger.from_settings()

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    tools = registry.litellm_schemas()

    for _turn in range(MAX_TURNS):
        # --- pre_model_call hooks (budget check happens here) ---
        try:
            budget.check()
            await hooks.fire_pre_model_call(session_id, messages, model)
        except BudgetExceededError as e:
            await hooks.fire_budget_exceeded(session_id, e.spent, e.limit)
            return f"[Budget exceeded: ${e.spent:.4f} / ${e.limit:.2f}]"

        # --- model call ---
        t0 = time.monotonic()
        response = await litellm.acompletion(
            model=model, messages=messages, tools=tools or None, tool_choice="auto"
        )
        latency_ms = (time.monotonic() - t0) * 1000

        # Accumulate cost from LiteLLM metadata
        cost = getattr(response, "_hidden_params", {}).get("response_cost", 0.0) or 0.0
        budget.record(cost)

        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0

        tracer.write(
            Span(
                trace_id=session_id,
                span_id=f"{session_id}-turn-{_turn}",
                name="model_call",
                input={"model": model, "messages": len(messages)},
                output={"tool_calls": len(response.choices[0].message.tool_calls or [])},
                metadata={
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_usd": cost,
                    "latency_ms": latency_ms,
                },
            )
        )

        msg = response.choices[0].message
        messages.append(msg.model_dump() if hasattr(msg, "model_dump") else dict(msg))

        # No tool calls -> final answer
        if not msg.tool_calls:
            return msg.content or ""

        # --- process tool calls ---
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            args: dict[str, Any] = json.loads(tc.function.arguments or "{}")

            if policy_engine is None:
                decision, reason = Decision.ALLOW, "no policy engine"
            else:
                decision, reason = policy_engine.evaluate(tool_name, args)

            args_hash = policy_engine.args_hash(args) if policy_engine else "nopolicy"
            approved_by_human = False

            if decision == Decision.DENY:
                tool_result = f"[DENIED: {reason}]"
                outcome = "denied"
            elif decision == Decision.REQUIRE_APPROVAL:
                approved_by_human = await hooks.fire_approval_needed(session_id, tool_name, args)
                if not approved_by_human:
                    tool_result = "[DENIED: human rejected approval]"
                    outcome = "denied"
                else:
                    tool_result, outcome = await _invoke_tool(
                        session_id, tool_name, args, latency_ms
                    )
            else:
                tool_result, outcome = await _invoke_tool(session_id, tool_name, args, latency_ms)

            # Audit
            event = AuditEvent(
                session_id=session_id,
                tool_name=tool_name,
                args_hash=args_hash,
                decision=decision.value,
                approved_by_human=approved_by_human,
                tokens_in=response.usage.prompt_tokens if response.usage else 0,
                tokens_out=response.usage.completion_tokens if response.usage else 0,
                cost_usd=cost,
                latency_ms=latency_ms,
                outcome=outcome,
            )
            audit_logger.record(event)

            tracer.write(
                Span(
                    trace_id=session_id,
                    span_id=f"{session_id}-tool-{tool_name}-{_turn}",
                    name="tool_call",
                    input={"tool": tool_name, "args_hash": args_hash},
                    output={"outcome": outcome, "result_len": len(str(tool_result))},
                    metadata={
                        "decision": decision.value,
                        "approved_by_human": approved_by_human,
                        "latency_ms": latency_ms,
                    },
                )
            )

            await hooks.fire_post_tool_call(session_id, tool_name, args, tool_result, latency_ms)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(tool_result),
                }
            )

    return "[Max turns reached]"


async def _invoke_tool(
    session_id: str, tool_name: str, args: dict[str, Any], latency_ms: float
) -> tuple[str, str]:
    try:
        await hooks.fire_pre_tool_call(session_id, tool_name, args)
        tool_def = registry.get(tool_name)
        result = await tool_def.handler(**args)
        return str(result), "ok"
    except KeyError:
        return f"[Tool '{tool_name}' not found]", "error"
    except Exception as e:
        return f"[Tool error: {e}]", "error"
