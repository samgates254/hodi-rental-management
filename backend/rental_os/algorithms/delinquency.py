"""Deterministic arrears state. No clock, no ledger writes.

A posted open balance is:

- CURRENT while as_of is on or before the due date
- GRACE_PERIOD while as_of is after the due date and on or before due + grace_days
- DELINQUENT after that

grace_days == 0 leaves no grace window: the next civil day is delinquent.
Dates are inclusive civil dates. No timezone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .money import require_cents


class DelinquencyError(ValueError):
    """Illegal delinquency input."""


CURRENT = "CURRENT"
GRACE_PERIOD = "GRACE_PERIOD"
DELINQUENT = "DELINQUENT"
SETTLED = "SETTLED"
EXCLUDED = "EXCLUDED"

_OPEN_LIFECYCLES = frozenset({"POSTED"})
_KNOWN_LIFECYCLES = frozenset({"DRAFT", "POSTED", "VOIDED", "WRITTEN_OFF"})
_RANK = {CURRENT: 0, GRACE_PERIOD: 1, DELINQUENT: 2}


@dataclass(frozen=True)
class Obligation:
    obligation_id: str
    due_date: date
    balance_cents: int
    lifecycle: str = "POSTED"


@dataclass(frozen=True)
class ObligationAssessment:
    obligation_id: str
    status: str
    balance_cents: int
    days_past_due: int


@dataclass(frozen=True)
class DelinquencyResult:
    status: str
    open_cents: int
    current_cents: int
    grace_cents: int
    delinquent_cents: int
    items: tuple[ObligationAssessment, ...]


def _assess_one(item: Obligation, as_of: date, grace_days: int) -> ObligationAssessment:
    balance = require_cents(item.balance_cents, name="balance_cents")
    if item.lifecycle not in _KNOWN_LIFECYCLES:
        raise DelinquencyError(f"unknown lifecycle {item.lifecycle!r}")
    if not isinstance(item.due_date, date):
        raise DelinquencyError("due_date must be a date")
    if item.lifecycle not in _OPEN_LIFECYCLES or balance == 0:
        status = SETTLED if item.lifecycle in _OPEN_LIFECYCLES else EXCLUDED
        return ObligationAssessment(item.obligation_id, status, balance, 0)
    late = (as_of - item.due_date).days
    if late <= 0:
        status = CURRENT
        late = 0
    elif as_of <= item.due_date + timedelta(days=grace_days):
        status = GRACE_PERIOD
    else:
        status = DELINQUENT
    return ObligationAssessment(item.obligation_id, status, balance, late)


def assess_delinquency(
    obligations: list[Obligation] | tuple[Obligation, ...],
    *,
    as_of: date,
    grace_days: int,
) -> DelinquencyResult:
    """Classify posted open balances as of a caller-supplied civil date.

    Complexity: O(N). Portfolio status is the worst open item.
    """
    if not isinstance(as_of, date):
        raise DelinquencyError("as_of must be a date")
    if isinstance(grace_days, bool) or not isinstance(grace_days, int) or grace_days < 0:
        raise DelinquencyError("grace_days must be an int >= 0")
    seen: set[str] = set()
    items: list[ObligationAssessment] = []
    buckets = {CURRENT: 0, GRACE_PERIOD: 0, DELINQUENT: 0}
    for item in obligations:
        if not item.obligation_id:
            raise DelinquencyError("obligation_id is required")
        if item.obligation_id in seen:
            raise DelinquencyError(f"duplicate obligation_id {item.obligation_id}")
        seen.add(item.obligation_id)
        assessed = _assess_one(item, as_of, grace_days)
        items.append(assessed)
        if assessed.status in buckets:
            buckets[assessed.status] += assessed.balance_cents
    open_cents = buckets[CURRENT] + buckets[GRACE_PERIOD] + buckets[DELINQUENT]
    status = CURRENT
    for name, amount in buckets.items():
        if amount and _RANK[name] > _RANK[status]:
            status = name
    return DelinquencyResult(
        status=status,
        open_cents=open_cents,
        current_cents=buckets[CURRENT],
        grace_cents=buckets[GRACE_PERIOD],
        delinquent_cents=buckets[DELINQUENT],
        items=tuple(items),
    )
