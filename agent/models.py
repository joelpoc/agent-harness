"""
models — LiteLLM provider configuration.

Switching providers requires only changing MODEL env var or passing a different
model string. The rest of the agent loop is unchanged — that's the point.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supported: anthropic/claude-sonnet-*, vertex_ai/gemini-*, ollama/qwen2.5:7b
    default_model: str = Field(default="anthropic/claude-sonnet-4-5", alias="DEFAULT_MODEL")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    vertexai_project: str = Field(default="", alias="VERTEXAI_PROJECT")
    vertexai_location: str = Field(default="us-central1", alias="VERTEXAI_LOCATION")

    # Available model aliases for the demo
    PROVIDERS: dict[str, str] = {
        "claude": "anthropic/claude-sonnet-4-5",
        "gemini": "vertex_ai/gemini-2.0-flash",
        "ollama": "ollama/qwen2.5:7b",
    }


settings = ModelSettings()
