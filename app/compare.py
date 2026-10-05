"""Deterministic policy and attack-outcome diffs."""

from decimal import Decimal

from app.attacks import AttackResult, run_attacks
from app.engine import Policy
from app.money import as_money


def money_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(as_money(value), "f")


def field_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return money_text(value)
    if isinstance(value, (set, frozenset, list, tuple)):
        return ", ".join(sorted(str(item) for item in value))
    return str(value)


def changed_fields(old: Policy, new: Policy) -> list[dict[str, str | None]]:
    changes: list[dict[str, str | None]] = []
    for field in (
        "daily_limit",
        "approval_above",
        "rolling_hour_limit",
        "allowed_recipients",
        "allowed_start_hour",
        "allowed_end_hour",
        "per_recipient_daily_limit",
    ):
        before = getattr(old, field)
        after = getattr(new, field)
        if before != after:
            changes.append(
                {
                    "field": field,
                    "old": field_text(before),
                    "new": field_text(after),
                }
            )
    return changes


def changed_outcomes(
    old: Policy,
    new: Policy,
) -> list[dict[str, str]]:
    previous = {item.name: item.outcome for item in run_attacks(old)}
    current = {item.name: item.outcome for item in run_attacks(new)}
    changes: list[dict[str, str]] = []
    for name, before in previous.items():
        after = current[name]
        if before != after:
            changes.append({"name": name, "old": before, "new": after})
    return changes


def attack_payload(result: AttackResult) -> dict[str, object]:
    return {
        "name": result.name,
        "outcome": result.outcome,
        "explanation": result.explanation,
        "decisions": [
            {"status": item.status, "reasons": list(item.reasons)}
            for item in result.evaluations
        ],
        "payments": [
            {
                "amount": payment.amount,
                "time": payment.time,
                "status": evaluation.status,
                "reasons": list(evaluation.reasons),
            }
            for payment, evaluation in zip(result.payments, result.evaluations)
        ],
    }
