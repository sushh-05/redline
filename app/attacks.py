"""Deterministic attack scenarios for spending-policy simulation.

Each attack is a fixed payment sequence. Outcomes are derived only from
evaluate() results: blocked, escalated, escaped, or safe.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Sequence

from app.engine import Evaluation, Policy, Transaction, evaluate
from app.money import as_money

ZERO = Decimal("0.00")
Outcome = Literal["blocked", "escalated", "escaped", "safe"]
RECIPIENT = "merchant"
ATTACK_START = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Attack:
    name: str
    payments: tuple[Transaction, ...]


@dataclass(frozen=True)
class AttackResult:
    name: str
    outcome: Outcome
    explanation: str
    evaluations: tuple[Evaluation, ...]
    allowed_total: Decimal
    payments: tuple[Transaction, ...]


def split_second(start: datetime) -> Attack:
    payments = tuple(
        Transaction(
            amount=Decimal("4.99"),
            recipient=RECIPIENT,
            time=start + timedelta(minutes=8 * index),
        )
        for index in range(4)
    )
    return Attack(name="split-second", payments=payments)


def boundary(start: datetime) -> Attack:
    payments = tuple(
        Transaction(amount=Decimal(amount), recipient=RECIPIENT, time=start)
        for amount in ("4.99", "5.00", "5.01")
    )
    return Attack(name="boundary", payments=payments)


def velocity(start: datetime) -> Attack:
    payments = tuple(
        Transaction(
            amount=Decimal("1.50"),
            recipient=RECIPIENT,
            time=start + timedelta(seconds=30 * index),
        )
        for index in range(10)
    )
    return Attack(name="velocity", payments=payments)


def attacks(start: datetime) -> tuple[Attack, ...]:
    return (split_second(start), boundary(start), velocity(start))


def run_attack(policy: Policy, attack: Attack) -> AttackResult:
    evaluations: list[Evaluation] = []
    allowed_total = ZERO
    for index, payment in enumerate(attack.payments):
        result = evaluate(policy, payment, attack.payments[:index])
        evaluations.append(result)
        if result.status == "allow":
            allowed_total = as_money(allowed_total + as_money(payment.amount))

    outcome = _outcome(evaluations, allowed_total, policy)
    return AttackResult(
        name=attack.name,
        outcome=outcome,
        explanation=_explanation(attack, outcome, allowed_total),
        evaluations=tuple(evaluations),
        allowed_total=allowed_total,
        payments=attack.payments,
    )


def run_attacks(
    policy: Policy,
    start: datetime = ATTACK_START,
) -> tuple[AttackResult, ...]:
    return tuple(run_attack(policy, attack) for attack in attacks(start))


def _outcome(
    evaluations: Sequence[Evaluation],
    allowed_total: Decimal,
    policy: Policy,
) -> Outcome:
    if any(item.status == "block" for item in evaluations):
        return "blocked"
    if any(item.status == "review" for item in evaluations):
        return "escalated"
    twice_approval = as_money(as_money(policy.approval_above) + as_money(policy.approval_above))
    if allowed_total >= twice_approval:
        return "escaped"
    return "safe"


def _explanation(attack: Attack, outcome: Outcome, allowed_total: Decimal) -> str:
    count = len(attack.payments)
    amounts = [as_money(payment.amount) for payment in attack.payments]
    moved = format(allowed_total, "f")
    if outcome == "escaped" and amounts and all(amount == amounts[0] for amount in amounts):
        return (
            f"{count} payments of {format(amounts[0], 'f')} avoided approval "
            f"while moving {moved}."
        )
    if outcome == "escaped":
        return f"{count} payments avoided approval while moving {moved}."
    if outcome == "blocked":
        return "At least one payment was blocked."
    if outcome == "escalated":
        return "At least one payment needed review."
    return "All payments were allowed under twice the approval threshold."
