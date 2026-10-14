"""Integer money helpers. KES minor units only. No binary floating point."""

from __future__ import annotations

# Shared portable storage ceiling for monetary minor-unit fields backed by a
# signed SQLite/PostgreSQL BIGINT. Product-specific business caps may be lower.
MAX_MONEY_MINOR = (1 << 63) - 1


class MoneyError(ValueError):
    """Invalid monetary input."""


def require_cents(value: int, *, name: str, allow_zero: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MoneyError(f"{name} must be an int number of cents, got {type(value).__name__}")
    if value < 0 or (value == 0 and not allow_zero):
        raise MoneyError(f"{name} must be a non-negative int number of cents")
    return value


def round_half_up_div(numerator: int, denominator: int) -> int:
    """ROUND_HALF_UP of numerator/denominator for non-negative integers.

    (n + d//2) // d is half-up for positive n, d.
    """
    if isinstance(numerator, bool) or not isinstance(numerator, int):
        raise MoneyError("numerator must be int")
    if isinstance(denominator, bool) or not isinstance(denominator, int):
        raise MoneyError("denominator must be int")
    if numerator < 0 or denominator <= 0:
        raise MoneyError("round_half_up_div requires numerator >= 0 and denominator > 0")
    return (numerator + denominator // 2) // denominator
