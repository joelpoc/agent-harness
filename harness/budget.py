"""
budget — cost ceiling enforced by the shell.

Guarantee: no model call proceeds once the configured USD limit is reached.
The shell reads cost from LiteLLM response metadata — the model does not
self-report cost. Budget state is held in memory per session; reset on restart.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BudgetSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    budget_usd_limit: float = Field(default=1.0, alias="BUDGET_USD_LIMIT")


class BudgetExceededError(Exception):
    """Raised by the hook pipeline when the cost ceiling is reached."""

    def __init__(self, spent: float, limit: float) -> None:
        self.spent = spent
        self.limit = limit
        super().__init__(f"Budget exceeded: ${spent:.4f} / ${limit:.2f}")


class BudgetTracker:
    """Tracks cumulative cost for a session and enforces the ceiling."""

    def __init__(self, limit_usd: float) -> None:
        self._limit = limit_usd
        self._spent: float = 0.0

    @classmethod
    def from_settings(cls) -> BudgetTracker:
        settings = BudgetSettings()
        return cls(limit_usd=settings.budget_usd_limit)

    def record(self, cost_usd: float) -> None:
        """Add cost from a completed model call."""
        self._spent += cost_usd

    def check(self) -> None:
        """Raise BudgetExceededError if limit is reached."""
        if self._spent >= self._limit:
            raise BudgetExceededError(spent=self._spent, limit=self._limit)

    @property
    def spent(self) -> float:
        return self._spent

    @property
    def limit(self) -> float:
        return self._limit

    @property
    def remaining(self) -> float:
        return max(0.0, self._limit - self._spent)

    def summary(self) -> dict[str, float]:
        return {"spent": self._spent, "limit": self._limit, "remaining": self.remaining}
