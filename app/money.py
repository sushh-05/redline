from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

CENTS = Decimal("0.01")


def as_money(value: Decimal) -> Decimal:
    """Normalize a money value to two decimal places.

    Decisions never use binary floats. Banker's rounding keeps
    repeated simulations stable for the same inputs.
    """
    if not isinstance(value, Decimal):
        raise TypeError("money values must be decimal.Decimal")
    if not value.is_finite():
        raise ValueError("money values must be finite")
    return value.quantize(CENTS, rounding=ROUND_HALF_EVEN)


def parse_money(value: str | int | Decimal) -> Decimal:
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid money value") from exc
    return as_money(parsed)
