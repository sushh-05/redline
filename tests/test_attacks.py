from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.attacks import (
    Attack,
    boundary,
    run_attack,
    run_attacks,
    split_second,
    velocity,
)
from app.engine import Policy, Transaction

START = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def _policy(
    *,
    daily_limit: str = "100.00",
    approval_above: str = "5.00",
    rolling_hour_limit: str | None = None,
) -> Policy:
    return Policy(
        daily_limit=Decimal(daily_limit),
        approval_above=Decimal(approval_above),
        rolling_hour_limit=None if rolling_hour_limit is None else Decimal(rolling_hour_limit),
    )


def test_split_second_is_four_payments_of_4_99_eight_minutes_apart() -> None:
    payments = split_second(START).payments
    assert len(payments) == 4
    assert [payment.amount for payment in payments] == [Decimal("4.99")] * 4
    assert payments[1].time - payments[0].time == timedelta(minutes=8)
    assert payments[3].time - payments[0].time == timedelta(minutes=24)


def test_boundary_is_4_99_5_00_and_5_01() -> None:
    assert [payment.amount for payment in boundary(START).payments] == [
        Decimal("4.99"),
        Decimal("5.00"),
        Decimal("5.01"),
    ]


def test_velocity_is_ten_payments_of_1_50_within_five_minutes() -> None:
    payments = velocity(START).payments
    assert len(payments) == 10
    assert all(payment.amount == Decimal("1.50") for payment in payments)
    assert payments[-1].time - payments[0].time <= timedelta(minutes=5)


def test_split_second_escapes_when_all_allowed_total_is_twice_approval() -> None:
    result = run_attack(_policy(), split_second(START))
    assert result.outcome == "escaped"
    assert result.allowed_total == Decimal("19.96")
    assert result.explanation == "4 payments of 4.99 avoided approval while moving 19.96."
    assert all(item.status == "allow" for item in result.evaluations)


def test_boundary_is_escalated_because_5_01_needs_review() -> None:
    result = run_attack(_policy(), boundary(START))
    assert [item.status for item in result.evaluations] == ["allow", "allow", "review"]
    assert result.outcome == "escalated"
    assert result.explanation == "At least one payment needed review."


def test_velocity_escapes_when_small_payments_stay_under_approval() -> None:
    result = run_attack(_policy(), velocity(START))
    assert result.outcome == "escaped"
    assert result.allowed_total == Decimal("15.00")
    assert result.explanation == "10 payments of 1.50 avoided approval while moving 15.00."
    assert all(item.status == "allow" for item in result.evaluations)


def test_split_second_is_escalated_with_a_rolling_limit_of_10() -> None:
    result = run_attack(_policy(rolling_hour_limit="10.00"), split_second(START))
    assert result.outcome == "escalated"
    assert [item.status for item in result.evaluations] == [
        "allow",
        "allow",
        "review",
        "review",
    ]


def test_split_second_is_blocked_when_daily_limit_is_exceeded() -> None:
    result = run_attack(_policy(daily_limit="10.00"), split_second(START))
    assert result.outcome == "blocked"
    assert "block" in {item.status for item in result.evaluations}
    assert result.explanation == "At least one payment was blocked."


def test_safe_when_allowed_total_is_under_twice_approval() -> None:
    modest = Attack(
        name="modest",
        payments=(
            Transaction(amount=Decimal("4.99"), recipient="merchant", time=START),
        ),
    )
    result = run_attack(_policy(), modest)
    assert result.outcome == "safe"
    assert result.explanation == "All payments were allowed under twice the approval threshold."


def test_run_attacks_evaluates_each_sequence_with_history() -> None:
    results = run_attacks(_policy(), START)
    assert [item.name for item in results] == ["split-second", "boundary", "velocity"]
    assert [item.outcome for item in results] == ["escaped", "escalated", "escaped"]
    split = results[0]
    assert split.evaluations[0].status == "allow"
    assert len(split.evaluations) == 4
