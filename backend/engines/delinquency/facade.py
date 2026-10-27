"""Delinquency boundary. as_of is required. No clock. No formula."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from rental_os.algorithms.delinquency import (
    DelinquencyError,
    DelinquencyResult,
    Obligation,
    assess_delinquency,
)
from rental_os.algorithms.money import MoneyError


_FIELDS = ("obligation_id", "due_date", "balance_cents", "lifecycle")


@dataclass(frozen=True)
class DelinquencyObligation:
    obligation_id: str
    due_date: date
    balance_cents: int
    lifecycle: str


def _exact_date(value: object, name: str) -> date:
    if type(value) is not date:
        raise DelinquencyError(f"{name} must be an exact datetime.date")
    return value


def _mapping(value: DelinquencyObligation | Mapping[str, object]) -> Mapping[str, object]:
    if isinstance(value, DelinquencyObligation):
        return {name: getattr(value, name) for name in _FIELDS}
    if isinstance(value, Mapping):
        missing = [name for name in _FIELDS if name not in value]
        extra = sorted(set(value) - set(_FIELDS))
        if missing or extra:
            raise DelinquencyError(f"obligation fields invalid missing={missing} extra={extra}")
        return value
    raise DelinquencyError("obligation must be DelinquencyObligation or a complete mapping")


def _obligation(value: DelinquencyObligation | Mapping[str, object]) -> Obligation:
    data = _mapping(value)
    obligation_id = data["obligation_id"]
    if not isinstance(obligation_id, str) or obligation_id.strip() == "":
        raise DelinquencyError("obligation_id is required")
    lifecycle = data["lifecycle"]
    if not isinstance(lifecycle, str) or lifecycle.strip() == "":
        raise DelinquencyError("lifecycle is required")
    balance = data["balance_cents"]
    if isinstance(balance, bool) or not isinstance(balance, int):
        raise MoneyError(f"balance_cents must be an int number of cents, got {type(balance).__name__}")
    return Obligation(
        obligation_id=obligation_id,
        due_date=_exact_date(data["due_date"], "due_date"),
        balance_cents=balance,
        lifecycle=lifecycle,
    )


def assess(
    *,
    obligations: list[DelinquencyObligation | Mapping[str, object]]
    | tuple[DelinquencyObligation | Mapping[str, object], ...],
    as_of: date,
    grace_days: int,
) -> DelinquencyResult:
    """Classify balances as of the caller-supplied civil date."""
    as_of_date = _exact_date(as_of, "as_of")
    if isinstance(grace_days, bool) or not isinstance(grace_days, int):
        raise DelinquencyError("grace_days must be an int >= 0")
    if not isinstance(obligations, (list, tuple)):
        raise DelinquencyError("obligations must be a list or tuple")
    rows = [_obligation(item) for item in obligations]
    return assess_delinquency(rows, as_of=as_of_date, grace_days=grace_days)


__all__ = [
    "DelinquencyError",
    "DelinquencyObligation",
    "MoneyError",
    "assess",
]
