"""Pull policy limits out of a sentence with keyword matching only."""

import re
from dataclasses import dataclass
from decimal import Decimal

from app.money import parse_money

_TAIL = r"(?:\s+(?:of|to|is|at))?\s*[:=]?\s*\$?(\d+(?:\.\d+)?)"

_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "daily_limit",
        ("daily limit", "daily_limit", "daily-limit"),
    ),
    (
        "approval_above",
        ("approval above", "approval_above", "approval-above"),
    ),
    (
        "rolling_hour_limit",
        (
            "rolling hour limit",
            "rolling_hour_limit",
            "rolling-hour limit",
            "rolling hour",
        ),
    ),
)


@dataclass(frozen=True)
class ParsedPolicy:
    daily_limit: Decimal | None
    approval_above: Decimal | None
    rolling_hour_limit: Decimal | None


def parse_policy_sentence(sentence: str) -> ParsedPolicy:
    text = sentence.lower()
    found: dict[str, Decimal | None] = {
        "daily_limit": None,
        "approval_above": None,
        "rolling_hour_limit": None,
    }
    for field, phrases in _KEYWORDS:
        found[field] = _first_number_after(text, phrases)
    return ParsedPolicy(
        daily_limit=found["daily_limit"],
        approval_above=found["approval_above"],
        rolling_hour_limit=found["rolling_hour_limit"],
    )


def _first_number_after(text: str, phrases: tuple[str, ...]) -> Decimal | None:
    for phrase in phrases:
        match = re.search(re.escape(phrase) + _TAIL, text)
        if match:
            return parse_money(match.group(1))
    return None
