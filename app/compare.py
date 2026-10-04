"""Deterministic policy and attack-outcome diffs."""

from decimal import Decimal

from app.attacks import AttackResult, run_attacks
from app.engine import Policy
from app.money import as_money


def money_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(as_money(value), "f")


def changed_fields(old: Policy, new: Policy) -> list[dict[str, str | None]]:
    changes: list[dict[str, str | None]] = []
    for field in ("daily_limit", "approval_above", "rolling_hour_limit"):
        before = getattr(old, field)
        after = getattr(new, field)
        if before != after:
            changes.append(
                {
                    "field": field,
                    "old": money_text(before),
                    "new": money_text(after),
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
    }
