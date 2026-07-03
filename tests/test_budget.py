"""Unit tests for the budget tracker."""

from __future__ import annotations

import pytest

from harness.budget import BudgetExceededError, BudgetTracker


def test_initial_state() -> None:
    tracker = BudgetTracker(limit_usd=1.0)
    assert tracker.spent == 0.0
    assert tracker.remaining == 1.0


def test_record_cost() -> None:
    tracker = BudgetTracker(limit_usd=1.0)
    tracker.record(0.25)
    assert tracker.spent == pytest.approx(0.25)
    assert tracker.remaining == pytest.approx(0.75)


def test_check_does_not_raise_when_under_limit() -> None:
    tracker = BudgetTracker(limit_usd=1.0)
    tracker.record(0.99)
    tracker.check()  # should not raise


def test_check_raises_when_at_limit() -> None:
    tracker = BudgetTracker(limit_usd=1.0)
    tracker.record(1.0)
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.check()
    assert exc_info.value.spent == pytest.approx(1.0)
    assert exc_info.value.limit == pytest.approx(1.0)


def test_check_raises_when_over_limit() -> None:
    tracker = BudgetTracker(limit_usd=0.5)
    tracker.record(0.3)
    tracker.record(0.3)
    with pytest.raises(BudgetExceededError):
        tracker.check()


def test_summary() -> None:
    tracker = BudgetTracker(limit_usd=2.0)
    tracker.record(0.5)
    summary = tracker.summary()
    assert summary["spent"] == pytest.approx(0.5)
    assert summary["limit"] == pytest.approx(2.0)
    assert summary["remaining"] == pytest.approx(1.5)
