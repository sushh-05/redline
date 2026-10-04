"""Pull policy limits out of a sentence with keyword matching only."""

import re
from dataclasses import dataclass
from decimal import Decimal

from app.money import parse_money

_TAIL = r"(?:\s+(?:of|to|is|at))?\s*[:=]?\s*\$?(\d+(?:\.\d+)?)"

_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "daily_limit",
        (
            "daily limit",
            "daily spending limit",
            "daily spend limit",
            "daily budget",
            "daily cap",
            "daily_limit",
            "daily-limit",
        ),
    ),
    (
        "approval_above",
        (
            "approval above",
            "approval over",
            "approval greater than",
            "approval required above",
            "approval required over",
            "approval_above",
            "approval-above",
            "purchases over",
        ),
    ),
    (
        "rolling_hour_limit",
        (
            "rolling hour limit",
            "rolling hourly limit",
            "hourly limit",
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
    text = re.sub(r"\s+", " ", sentence.lower()).strip()
    found: dict[str, Decimal | None] = {
        "daily_limit": None,
        "approval_above": None,
        "rolling_hour_limit": None,
    }
    for field, phrases in _KEYWORDS:
        found[field] = _first_number_after(text, phrases)

    # Also accept natural phrasing where the amount comes before the limit
    # phrase, for example: "spend up to $100 per day".
    if found["daily_limit"] is None:
        found["daily_limit"] = _first_number(text, (r"spend(?:ing)?\s+up\s+to", r"up\s+to"))
    if found["approval_above"] is None:
        found["approval_above"] = _first_number(text, (r"require(?:s)?\s+approval\s+for\s+(?:any\s+)?(?:purchase|payment)s?\s+over",))
    if found["rolling_hour_limit"] is None:
        found["rolling_hour_limit"] = _first_number(
            text,
            (r"(?:limit|cap)\s+of", r"cap\s+spending\s+at"),
        )
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


def _first_number(text: str, prefixes: tuple[str, ...]) -> Decimal | None:
    for prefix in prefixes:
        match = re.search(prefix + r"\s*[:=]?\s*\$?(\d+(?:\.\d+)?)", text)
        if match:
            return parse_money(match.group(1))
    return None
