"""
tracing — structured span writing via OpenTelemetry (Phoenix) and local JSONL.

Guarantee: every span is written to local JSONL always (zero-dependency path).
When PHOENIX_ENABLED=true, LiteLLM is auto-instrumented via OpenInference and
spans are sent over OTLP to a Phoenix server at PHOENIX_COLLECTOR_ENDPOINT.

The OTLP endpoint is backend-agnostic — any OpenTelemetry-compatible collector
(Jaeger, Grafana Tempo, Honeycomb, Phoenix) can receive these traces without
code changes. The agent session is never blocked by a tracing failure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TracingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    local_traces_path: Path = Field(default=Path("traces.jsonl"), alias="LOCAL_TRACES_PATH")
    phoenix_enabled: bool = Field(default=False, alias="PHOENIX_ENABLED")
    # OTLP-standard endpoint — works with Phoenix, Jaeger, Grafana Tempo, etc.
    phoenix_collector_endpoint: str = Field(
        default="http://localhost:6006/v1/traces",
        alias="PHOENIX_COLLECTOR_ENDPOINT",
    )


class Span(BaseModel):
    trace_id: str
    span_id: str
    name: str
    start_time: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    end_time: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    level: str = "DEFAULT"  # DEFAULT | DEBUG | WARNING | ERROR


class Tracer:
    """
    Writes spans to local JSONL (always) and Phoenix via OTLP (when enabled).

    Phoenix instrumentation auto-traces every LiteLLM call via OpenInference —
    no per-call code needed beyond enabling it at startup.
    """

    def __init__(self, settings: TracingSettings | None = None) -> None:
        self._settings = settings or TracingSettings()
        self._local_path = self._settings.local_traces_path
        self._local_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_otel_phoenix()

    def _init_otel_phoenix(self) -> None:
        """
        Instrument LiteLLM via OpenInference and register an OTLP exporter
        pointing at Phoenix (or any OTel-compatible backend).

        Uses phoenix.otel.register() — a thin convenience wrapper around the
        standard OTel SDK. The endpoint is OTLP/HTTP, not Phoenix-proprietary.
        """
        if not self._settings.phoenix_enabled:
            return
        try:
            from openinference.instrumentation.litellm import (  # type: ignore[import-untyped]
                LiteLLMInstrumentor,
            )
            from phoenix.otel import register  # type: ignore[import-untyped]

            register(
                endpoint=self._settings.phoenix_collector_endpoint,
                project_name="agent-harness",
            )
            LiteLLMInstrumentor().instrument()
        except Exception:
            pass  # Never block on tracing failure

    def write(self, span: Span) -> None:
        """Write span to local JSONL. OTel spans flow automatically via instrumentation."""
        self._write_local(span)

    def _write_local(self, span: Span) -> None:
        with self._local_path.open("a") as f:
            f.write(span.model_dump_json() + "\n")


# Global tracer — initialised at startup
tracer = Tracer()
