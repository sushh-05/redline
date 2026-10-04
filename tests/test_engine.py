from datetime import datetime, timedelta, timezone
from decimal import Decimal
from inspect import getsource

from fastapi.testclient import TestClient

from app import engine
from app.engine import Policy, Transaction, evaluate
from app.main import app
from app.money import as_money

client = TestClient(app)

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

POLICY = Policy(
    daily_limit=Decimal("80.00"),
    approval_above=Decimal("25.00"),
    rolling_hour_limit=Decimal("40.00"),
)


def _txn(
    amount: str,
    *,
    when: datetime = NOW,
    recipient: str = "bookstore",
) -> Transaction:
    return Transaction(amount=Decimal(amount), recipient=recipient, time=when)


def test_allow_within_policy() -> None:
    result = evaluate(POLICY, _txn("10.00"), ())
    assert result.status == "allow"
    assert result.reasons == ()


def test_review_when_amount_above_approval() -> None:
    result = evaluate(POLICY, _txn("40.00"), ())
    assert result.status == "review"
    assert result.reasons == ("amount_above_approval",)


def test_block_when_daily_total_exceeds_limit() -> None:
    history = (_txn("50.00", when=NOW - timedelta(hours=3)),)
    result = evaluate(POLICY, _txn("40.00"), history)
    assert result.status == "block"
    assert "daily_limit_exceeded" in result.reasons


def test_prior_day_does_not_count_toward_daily_limit() -> None:
    history = (_txn("80.00", when=NOW - timedelta(days=1)),)
    result = evaluate(POLICY, _txn("10.00"), history)
    assert result.status == "allow"
    assert result.reasons == ()


def test_review_when_rolling_hour_total_exceeds_limit() -> None:
    history = (_txn("30.00", when=NOW - timedelta(minutes=20)),)
    result = evaluate(POLICY, _txn("15.00"), history)
    assert result.status == "review"
    assert result.reasons == ("rolling_hour_limit_exceeded",)


def test_history_older_than_one_hour_is_outside_rolling_window() -> None:
    history = (_txn("39.00", when=NOW - timedelta(hours=1, seconds=1)),)
    result = evaluate(POLICY, _txn("10.00"), history)
    assert result.status == "allow"
    assert result.reasons == ()


def test_returns_every_triggered_reason() -> None:
    history = (
        _txn("50.00", when=NOW - timedelta(minutes=10)),
        _txn("20.00", when=NOW - timedelta(minutes=5)),
    )
    result = evaluate(POLICY, _txn("30.00"), history)
    assert result.status == "block"
    assert result.reasons == (
        "daily_limit_exceeded",
        "rolling_hour_limit_exceeded",
        "amount_above_approval",
    )


def test_rolling_hour_limit_is_optional() -> None:
    policy = Policy(daily_limit=Decimal("80.00"), approval_above=Decimal("25.00"))
    history = (_txn("30.00", when=NOW - timedelta(minutes=10)),)
    result = evaluate(policy, _txn("15.00"), history)
    assert result.status == "allow"
    assert result.reasons == ()


def test_same_inputs_always_produce_the_same_decision() -> None:
    history = (_txn("30.00", when=NOW - timedelta(minutes=10)),)
    first = evaluate(POLICY, _txn("15.00"), history)
    second = evaluate(POLICY, _txn("15.00"), history)
    assert first == second


def test_money_is_decimal_not_float() -> None:
    total = as_money(Decimal("0.10") + Decimal("0.20"))
    assert total == Decimal("0.30")
    assert isinstance(total, Decimal)


def test_evaluate_endpoint() -> None:
    response = client.post(
        "/evaluate",
        json={
            "policy": {
                "daily_limit": "80.00",
                "approval_above": "25.00",
                "rolling_hour_limit": "40.00",
            },
            "transaction": {
                "amount": "12.50",
                "recipient": "bookstore",
                "time": "2026-10-05T12:00:00Z",
            },
            "history": [],
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "allow", "reasons": []}


def test_decision_source_is_deterministic() -> None:
    source = getsource(engine)
    forbidden = ("openai", "anthropic", "random", "uuid", "choice(")
    lowered = source.lower()
    for token in forbidden:
        assert token not in lowered
