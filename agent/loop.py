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

try:
    from openinference.instrumentation import using_session
    from openinference.semconv.trace import SpanAttributes
    from opentelemetry import trace as otel_trace

    _otel_tracer = otel_trace.get_tracer(__name__)
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False

MAX_TURNS = 20


async def run(
    user_message: str,
    model: str | None = None,
    session_id: str | None = None,
    policy_engine: PolicyEngine | None = None,
    budget: BudgetTracker | None = None,
    audit_logger: AuditLogger | None = None,
    history: list[dict[str, Any]] | None = None,
    system_prompt: str | None = None,
) -> str:
    """Run the agent loop for a single user message. Returns final text response.

    Pass `history` to maintain multi-turn conversation context across calls.
    history should be a list of prior {role, content} pairs (user + assistant),
    accumulated by the caller after each turn.
    Pass `system_prompt` to override the default system message (e.g. for demo scenarios).
    """
    model = model or model_settings.default_model
    session_id = session_id or str(uuid.uuid4())[:8]
    budget = budget or BudgetTracker.from_settings()
    audit_logger = audit_logger or AuditLogger.from_settings()

    # When Phoenix is enabled, wrap the session in an OTel agent span so all
    # turns and tool calls are grouped under one session_id in the Phoenix UI.
    if _OTEL_AVAILABLE and tracer.phoenix_enabled:
        with _otel_tracer.start_as_current_span(
            "agent",
            attributes={SpanAttributes.OPENINFERENCE_SPAN_KIND: "agent"},
        ) as span:
            span.set_attribute(SpanAttributes.SESSION_ID, session_id)
            span.set_attribute(SpanAttributes.INPUT_VALUE, user_message)
            with using_session(session_id):
                result = await _run_loop(
                    user_message=user_message,
                    model=model,
                    session_id=session_id,
                    policy_engine=policy_engine,
                    budget=budget,
                    audit_logger=audit_logger,
                    history=history,
                    system_prompt=system_prompt,
                )
            span.set_attribute(SpanAttributes.OUTPUT_VALUE, result)
        return result

    return await _run_loop(
        user_message=user_message,
        model=model,
        session_id=session_id,
        policy_engine=policy_engine,
        budget=budget,
        audit_logger=audit_logger,
        history=history,
        system_prompt=system_prompt,
    )


_DEFAULT_SYSTEM_PROMPT = (
    "You are a data analysis assistant with access to a GCP billing warehouse. "
    "Available tools: describe_schema (get table columns), query_data (run SQL), "
    "generate_report (format output), create_ticket (requires human approval). "
    "The warehouse contains ~90 days of GCP billing data. "
    "Always use DuckDB date functions for relative time ranges — never hardcode dates. "
    "Examples: last 30 days → date >= CURRENT_DATE - INTERVAL '30 days'; "
    "last month → date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month') "
    "AND date < DATE_TRUNC('month', CURRENT_DATE); "
    "this month → date >= DATE_TRUNC('month', CURRENT_DATE). "
    "Always use tools to get real data — never guess or estimate numbers. "
    "Once you have the data needed, respond with a clear text answer and stop calling tools."
)


async def _run_loop(
    user_message: str,
    model: str,
    session_id: str,
    policy_engine: PolicyEngine | None,
    budget: BudgetTracker,
    audit_logger: AuditLogger,
    history: list[dict[str, Any]] | None,
    system_prompt: str | None = None,
) -> str:
    """Inner loop — separated so run() can wrap it in an OTel session span."""
    system_message: dict[str, Any] = {
        "role": "system",
        "content": system_prompt or _DEFAULT_SYSTEM_PROMPT,
    }
    messages: list[dict[str, Any]] = (
        [system_message, *history, {"role": "user", "content": user_message}]
        if history
        else [system_message, {"role": "user", "content": user_message}]
    )
    tools = registry.litellm_schemas()
    _seen_calls: set[str] = set()  # loop detection: (tool_name, args_json)

    for _turn in range(MAX_TURNS):
        # --- pre_model_call hooks (budget check happens here) ---
        try:
            budget.check()
            await hooks.fire_pre_model_call(session_id, messages, model)
        except BudgetExceededError as e:
            await hooks.fire_budget_exceeded(session_id, e.spent, e.limit)
            return f"[Budget exceeded: ${e.spent:.4f} / ${e.limit:.2f}]"

        # --- model call ---
        # drop_params=True silently removes unsupported params (e.g. tool_choice
        # is not supported by Ollama) instead of raising UnsupportedParamsError.
        t0 = time.monotonic()
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            tools=tools or None,
            tool_choice="auto",
            drop_params=True,
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

        # --- loop detection: if all tool calls have been seen before, force final answer ---
        call_keys = [f"{tc.function.name}:{tc.function.arguments}" for tc in msg.tool_calls]
        if all(k in _seen_calls for k in call_keys):
            nudge = (
                "You have all the data. Provide your final text answer now — no more tool calls."
            )
            messages.append({"role": "user", "content": nudge})
            continue
        for k in call_keys:
            _seen_calls.add(k)

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
