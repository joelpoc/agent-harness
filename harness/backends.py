"""
backends — configuration for swappable ticketing backends.

Guarantee: TICKETS_BACKEND selects the implementation; the agent loop,
policy engine, and audit log are unaware of which backend is active.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "mock" (default, offline) or "github" (real GitHub issues via MCP)
    tickets_backend: str = Field(default="mock", alias="TICKETS_BACKEND")

    # GitHub MCP — fine-grained PAT, issues-only, single repo
    github_token: str = Field(default="", alias="GITHUB_PERSONAL_ACCESS_TOKEN")
    github_repo_owner: str = Field(default="", alias="GITHUB_REPO_OWNER")
    github_repo_name: str = Field(default="", alias="GITHUB_REPO_NAME")

    # Binary name for github-mcp-server (see ADR 008 for install instructions)
    github_mcp_command: str = Field(default="github-mcp-server", alias="GITHUB_MCP_COMMAND")
