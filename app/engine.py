"""Deterministic spending-policy engine.

Only this module may produce allow, review, or block. It uses
fixed Decimal comparisons and time windows. No model or LLM is
consulted for a decision.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal, Sequence

from app.money import as_money

ZERO = Decimal("0.00")
Status = Literal["allow", "review", "block"]

DAILY_LIMIT_EXCEEDED = "daily_limit_exceeded"
ROLLING_HOUR_LIMIT_EXCEEDED = "rolling_hour_limit_exceeded"
AMOUNT_ABOVE_APPROVAL = "amount_above_approval"


@dataclass(frozen=True)
class Policy:
    daily_limit: Decimal
    approval_above: Decimal
    rolling_hour_limit: Decimal | None = None


@dataclass(frozen=True)
class Transaction:
    amount: Decimal
    recipient: str
    time: datetime


@dataclass(frozen=True)
class Evaluation:
    status: Status
    reasons: tuple[str, ...]


def _on_same_day(left: datetime, right: datetime) -> bool:
    return left.date() == right.date()


def _in_rolling_hour(candidate: datetime, current: datetime) -> bool:
    return current - timedelta(hours=1) <= candidate <= current


def _total(transactions: Sequence[Transaction]) -> Decimal:
    running = ZERO
    for item in transactions:
        running = as_money(running + as_money(item.amount))
    return running


def evaluate(
    policy: Policy,
    transaction: Transaction,
    history: Sequence[Transaction],
) -> Evaluation:
    """Decide allow, review, or block from policy, the new spend, and history.

    Daily totals include the new transaction and same-calendar-day history.
    Rolling-hour totals include the new transaction and history in the prior hour.
    Every matching reason is returned; status is the most severe match.
    """
    amount = as_money(transaction.amount)
    reasons: list[str] = []

    daily_history = [
        item
        for item in history
        if _on_same_day(item.time, transaction.time) and item.time <= transaction.time
    ]
    daily_total = as_money(_total(daily_history) + amount)
    if daily_total > as_money(policy.daily_limit):
        reasons.append(DAILY_LIMIT_EXCEEDED)

    if policy.rolling_hour_limit is not None:
        hour_history = [
            item
            for item in history
            if _in_rolling_hour(item.time, transaction.time)
        ]
        hour_total = as_money(_total(hour_history) + amount)
        if hour_total > as_money(policy.rolling_hour_limit):
            reasons.append(ROLLING_HOUR_LIMIT_EXCEEDED)

    if amount > as_money(policy.approval_above):
        reasons.append(AMOUNT_ABOVE_APPROVAL)

    if DAILY_LIMIT_EXCEEDED in reasons:
        status: Status = "block"
    elif reasons:
        status = "review"
    else:
        status = "allow"

    return Evaluation(status=status, reasons=tuple(reasons))
