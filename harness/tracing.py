"""
tracing — structured span writing to Langfuse (cloud) and local JSONL.

Guarantee: every span is written to both sinks simultaneously. If Langfuse
is unavailable (missing keys, network error), local tracing continues
uninterrupted — the agent session is never blocked by a tracing failure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TracingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")
    local_traces_path: Path = Field(default=Path("traces.jsonl"), alias="LOCAL_TRACES_PATH")
    phoenix_enabled: bool = Field(default=False, alias="PHOENIX_ENABLED")


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
    """Writes spans to Langfuse + local JSONL."""

    def __init__(self, settings: TracingSettings | None = None) -> None:
        self._settings = settings or TracingSettings()
        self._langfuse: Any = None
        self._local_path = self._settings.local_traces_path
        self._local_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_langfuse()
        self._init_phoenix()

    def _init_phoenix(self) -> None:
        if not self._settings.phoenix_enabled:
            return
        try:
            import phoenix as px  # type: ignore[import-untyped]
            from openinference.instrumentation.litellm import (
                LiteLLMInstrumentor,  # type: ignore[import-untyped]
            )

            px.launch_app()
            LiteLLMInstrumentor().instrument()
        except Exception:
            pass  # Phoenix unavailable — continue without it

    def _init_langfuse(self) -> None:
        if self._settings.langfuse_public_key and self._settings.langfuse_secret_key:
            try:
                from langfuse import Langfuse  # type: ignore[import-untyped]

                self._langfuse = Langfuse(
                    public_key=self._settings.langfuse_public_key,
                    secret_key=self._settings.langfuse_secret_key,
                    host=self._settings.langfuse_host,
                )
            except Exception:
                pass  # Langfuse unavailable — local-only mode

    def write(self, span: Span) -> None:
        self._write_local(span)
        self._write_langfuse(span)

    def _write_local(self, span: Span) -> None:
        with self._local_path.open("a") as f:
            f.write(span.model_dump_json() + "\n")

    def _write_langfuse(self, span: Span) -> None:
        if self._langfuse is None:
            return
        try:
            self._langfuse.trace(
                id=span.trace_id,
                name=span.name,
                input=span.input,
                output=span.output,
                metadata=span.metadata,
            )
        except Exception:
            pass  # Never block on Langfuse failure


# Global tracer — initialised at startup
tracer = Tracer()
