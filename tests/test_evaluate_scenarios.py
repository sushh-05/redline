from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.engine import Policy, Transaction, evaluate

START = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
RECIPIENT = "merchant"


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


def _payment(amount: str, when: datetime) -> Transaction:
    return Transaction(amount=Decimal(amount), recipient=RECIPIENT, time=when)


def _four_payments_eight_minutes_apart() -> list[Transaction]:
    return [
        _payment("4.99", START + timedelta(minutes=8 * index))
        for index in range(4)
    ]


def _statuses(policy: Policy, payments: list[Transaction]) -> list[str]:
    return [
        evaluate(policy, payment, payments[:index]).status
        for index, payment in enumerate(payments)
    ]


def test_payment_of_4_99_is_allowed() -> None:
    result = evaluate(_policy(), _payment("4.99", START), ())
    assert result.status == "allow"
    assert result.reasons == ()


def test_payment_of_5_01_needs_review() -> None:
    result = evaluate(_policy(), _payment("5.01", START), ())
    assert result.status == "review"
    assert result.reasons == ("amount_above_approval",)


def test_exceeding_the_daily_limit_is_blocked() -> None:
    history = (_payment("6.00", START - timedelta(hours=2)),)
    result = evaluate(_policy(daily_limit="10.00"), _payment("4.99", START), history)
    assert result.status == "block"
    assert result.reasons == ("daily_limit_exceeded",)


def test_four_payments_of_4_99_allowed_when_there_is_no_rolling_limit() -> None:
    payments = _four_payments_eight_minutes_apart()
    assert _statuses(_policy(), payments) == ["allow", "allow", "allow", "allow"]


def test_four_payments_of_4_99_third_needs_review_when_rolling_limit_is_10() -> None:
    payments = _four_payments_eight_minutes_apart()
    statuses = _statuses(_policy(rolling_hour_limit="10.00"), payments)
    assert statuses[0] == "allow"
    assert statuses[1] == "allow"
    assert statuses[2] == "review"
    assert evaluate(
        _policy(rolling_hour_limit="10.00"),
        payments[2],
        payments[:2],
    ).reasons == ("rolling_hour_limit_exceeded",)
