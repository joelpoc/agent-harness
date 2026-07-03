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

    # Supported model strings:
    #   gemini/gemini-2.5-pro              → GEMINI_API_KEY (Google AI Studio — best)
    #   gemini/gemini-2.5-flash            → GEMINI_API_KEY (Google AI Studio — fast default)
    #   anthropic/claude-sonnet-4-5        → ANTHROPIC_API_KEY
    #   vertex_ai/gemini-2.5-pro           → GOOGLE_APPLICATION_CREDENTIALS (Vertex AI)
    #   ollama/qwen2.5:7b                  → local Ollama (air-gapped path)
    #
    # AI Studio vs Vertex: prefix gemini/ uses GEMINI_API_KEY (free tier OK);
    # prefix vertex_ai/ uses service account — do NOT mix them up.
    default_model: str = Field(default="gemini/gemini-2.5-flash", alias="DEFAULT_MODEL")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    vertexai_project: str = Field(default="", alias="VERTEXAI_PROJECT")
    vertexai_location: str = Field(default="us-central1", alias="VERTEXAI_LOCATION")

    # Named aliases for the model-flip demo
    PROVIDERS: dict[str, str] = {
        "gemini-pro": "gemini/gemini-2.5-pro",  # AI Studio — most capable
        "gemini-flash": "gemini/gemini-2.5-flash",  # AI Studio — fast default
        "claude": "anthropic/claude-sonnet-4-5",
        "gemini-vertex": "vertex_ai/gemini-2.5-pro",  # Vertex AI (service account)
        "ollama": "ollama/qwen2.5:7b",  # air-gapped
    }


settings = ModelSettings()
