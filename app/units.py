"""Human-readable unit labels for the synthetic catalogue."""

from decimal import Decimal, InvalidOperation

_SINGULAR = {"pieces": "piece", "piece": "piece"}
_PLURAL = {"piece": "pieces", "pieces": "pieces", "kg": "kg"}


def unit_word(value, unit: str) -> str:
    key = (unit or "unit").strip().lower()
    try:
        count = Decimal(str(value))
    except InvalidOperation:
        count = Decimal(0)
    if count == 1:
        return _SINGULAR.get(key, key)
    return _PLURAL.get(key, key if key.endswith("s") else f"{key}s")


def format_units(value, unit: str) -> str:
    return f"{value} {unit_word(value, unit)}"
