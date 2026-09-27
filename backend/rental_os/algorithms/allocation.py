"""Deterministic payment allocation.

Canonical priority (governing rule, lower class is paid first):

    1. Utilities
    2. Mandatory services
    3. Penalties
    4. Base rent
    5. Deposits and miscellaneous

Within a class, FIFO by due date, then period start, then UUID bytes.

This supersedes financial_mvp AllocationEngine.DEFAULT_RANK_VECTOR v1, which
pays RENT before WATER. Do not rewrite policy version 1 rows. New allocations
must stamp CANONICAL_POLICY_ID / CANONICAL_POLICY_VERSION.

LEGACY_V1_RANK is a locked exhibit of that defect. It is not an executable
policy. allocate_payment does not read it. Production calls cannot select it.

Overpayment is tenant prepaid rent, account 2020. Frozen COA assigns 2030 to
landlord funds held in trust. Blueprint text that says "Liability 2030" for
tenant overpayment conflicts with that COA and must not be followed.

The function is pure. Idempotency, row locks, and the journal append belong to
the caller. Lock order at the caller: Tenant, Payment, Invoice, Item.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from enum import Enum
from types import MappingProxyType

from .money import require_cents


CANONICAL_POLICY_ID = "CANONICAL_PRIORITY"
CANONICAL_POLICY_VERSION = 2

# financial_mvp v1 ranks. Retained only so tests can show the defect.
# MappingProxyType: readable, not assignable, not an allocation input.
LEGACY_V1_RANK = MappingProxyType(
    {
        "RENT": 10,
        "WATER": 20,
        "ELECTRICITY": 30,
        "SERVICE_CHARGE": 40,
        "PENALTY": 50,
        "OTHER": 99,
    }
)

CLASS_UTILITIES = 1
CLASS_MANDATORY = 2
CLASS_PENALTY = 3
CLASS_RENT = 4
CLASS_DEPOSIT_MISC = 5

CHARGE_CLASS = {
    "WATER": CLASS_UTILITIES,
    "ELECTRICITY": CLASS_UTILITIES,
    "SEWER": CLASS_UTILITIES,
    "GAS": CLASS_UTILITIES,
    "UTILITY": CLASS_UTILITIES,
    "SERVICE_CHARGE": CLASS_MANDATORY,
    "GARBAGE": CLASS_MANDATORY,
    "SECURITY": CLASS_MANDATORY,
    "MANDATORY_SERVICE": CLASS_MANDATORY,
    "PENALTY": CLASS_PENALTY,
    "LATE_FEE": CLASS_PENALTY,
    "FINE": CLASS_PENALTY,
    "RENT": CLASS_RENT,
    "BASE_RENT": CLASS_RENT,
    "DEPOSIT": CLASS_DEPOSIT_MISC,
    "SECURITY_DEPOSIT": CLASS_DEPOSIT_MISC,
    "MISC": CLASS_DEPOSIT_MISC,
    "OTHER": CLASS_DEPOSIT_MISC,
}

# Suspense, AR, prepaid rent. Not landlord trust 2030.
ACCT_SUSPENSE = "2050"
ACCT_AR = "1100"
ACCT_PREPAID_RENT = "2020"


class AllocationError(ValueError):
    """Rejected allocation input or broken invariant."""


class AllocationState(str, Enum):
    ZERO_PAYMENT = "ZERO_PAYMENT"
    FULLY_ALLOCATED = "FULLY_ALLOCATED"
    OVERPAID = "OVERPAID"


@dataclass(frozen=True)
class OpenItem:
    item_id: str
    invoice_id: str
    tenant_id: str
    charge_type: str
    due_date: date
    balance_cents: int
    period_start: date | None = None
    currency: str = "KES"
    lifecycle: str = "POSTED"


@dataclass(frozen=True)
class AllocationLine:
    item_id: str
    invoice_id: str
    charge_type: str
    amount_cents: int
    priority_class: int
    policy_id: str
    policy_version: int


@dataclass(frozen=True)
class Posting:
    account: str
    direction: str
    amount_cents: int


@dataclass(frozen=True)
class AllocationResult:
    lines: tuple[AllocationLine, ...]
    allocated_cents: int
    overpayment_cents: int
    state: AllocationState
    postings: tuple[Posting, ...]
    policy_id: str
    policy_version: int


def charge_class(charge_type: str) -> int:
    key = (charge_type or "").strip().upper()
    if key not in CHARGE_CLASS:
        raise AllocationError(f"unknown charge type {charge_type!r}; refusing to guess a rank")
    return CHARGE_CLASS[key]


_UUID_HEX = re.compile(r"^[0-9a-fA-F]{32}$")


def parse_uuid(item_id: str) -> uuid.UUID:
    """Accept hyphenated, bare hex, URN, and braced forms. Identity is the 16 bytes.

    `urn:` / `uuid:` are only a prefix, not substrings. CPython's uuid.UUID
    deletes those substrings anywhere, so `...00000urn:0001` aliases item
    `...0001`. That alias is rejected here.
    """
    if not isinstance(item_id, str):
        raise AllocationError(f"item_id must be a UUID, got {item_id!r}")
    text = item_id.strip()
    if text.lower().startswith("urn:uuid:"):
        text = text[len("urn:uuid:") :]
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    hex_body = text.replace("-", "")
    if _UUID_HEX.fullmatch(hex_body) is None:
        raise AllocationError(f"item_id must be a UUID, got {item_id!r}")
    return uuid.UUID(hex=hex_body)


def require_exact_date(value: object, name: str) -> date:
    """Civil date only. datetime is a date subclass and is rejected."""
    if type(value) is not date:
        raise AllocationError(f"{name} must be an exact datetime.date")
    return value


def assert_production_policy(policy_id: str, policy_version: int) -> None:
    """Reject every policy other than CANONICAL_PRIORITY version 2.

    Does not rank charges. Does not read LEGACY_V1_RANK.
    """
    if isinstance(policy_version, bool) or not isinstance(policy_version, int):
        raise AllocationError("policy_version must be the integer 2")
    if not isinstance(policy_id, str):
        raise AllocationError("policy_id must be CANONICAL_PRIORITY")
    if policy_id != CANONICAL_POLICY_ID or policy_version != CANONICAL_POLICY_VERSION:
        raise AllocationError("production allocation is locked to CANONICAL_PRIORITY version 2")


def allocation_sort_key(item: OpenItem) -> tuple:
    period = item.period_start or item.due_date
    return (charge_class(item.charge_type), item.due_date, period, parse_uuid(item.item_id).bytes)


def _postings(allocated: int, overpayment: int) -> tuple[Posting, ...]:
    rows: list[Posting] = []
    if allocated:
        rows.append(Posting(ACCT_SUSPENSE, "DEBIT", allocated))
        rows.append(Posting(ACCT_AR, "CREDIT", allocated))
    if overpayment:
        rows.append(Posting(ACCT_SUSPENSE, "DEBIT", overpayment))
        rows.append(Posting(ACCT_PREPAID_RENT, "CREDIT", overpayment))
    debits = sum(p.amount_cents for p in rows if p.direction == "DEBIT")
    credits = sum(p.amount_cents for p in rows if p.direction == "CREDIT")
    if debits != credits:
        raise AllocationError("postings do not balance")
    return tuple(rows)


def allocate_payment(
    *,
    payment_cents: int,
    tenant_id: str,
    currency: str,
    items: list[OpenItem] | tuple[OpenItem, ...],
    policy_id: str = CANONICAL_POLICY_ID,
    policy_version: int = CANONICAL_POLICY_VERSION,
) -> AllocationResult:
    """Allocate one payment across open POSTED items.

    Preconditions
    - payment_cents >= 0 integer cents
    - currency == 'KES'
    - every item is POSTED, same tenant, same currency, balance >= 0
    - item ids are unique UUIDs
    - charge types are in the canonical map
    - due_date and period_start are exact dates, not datetimes
    - policy is CANONICAL_PRIORITY version 2; any other policy is rejected
      before ranking

    Postconditions
    - sum(lines) == allocated_cents
    - allocated_cents + overpayment_cents == payment_cents
    - each line amount is in 1..item.balance
    - lines are in canonical order
    - postings balance (debits == credits)
    - remainder after open balances are exhausted is overpayment to 2020,
      never PARTIALLY_ALLOCATED and never landlord trust 2030

    Complexity: O(N log N) dominated by the sort.
    Concurrency: none. Caller serializes the tenant/payment/item rows.
    """
    assert_production_policy(policy_id, policy_version)
    amount = require_cents(payment_cents, name="payment_cents")
    if currency != "KES":
        raise AllocationError("currency isolation: only KES is accepted")
    if not tenant_id:
        raise AllocationError("tenant_id is required")

    seen: set[str] = set()
    for item in items:
        canonical = str(parse_uuid(item.item_id))
        if canonical in seen:
            raise AllocationError(f"duplicate item_id {item.item_id}")
        seen.add(canonical)
        if item.tenant_id != tenant_id:
            raise AllocationError("tenant isolation: item tenant does not match payment")
        if item.currency != "KES":
            raise AllocationError("currency isolation: item currency is not KES")
        if item.lifecycle != "POSTED":
            raise AllocationError(f"refusing to allocate against lifecycle {item.lifecycle}")
        require_cents(item.balance_cents, name="balance_cents")
        require_exact_date(item.due_date, "due_date")
        if item.period_start is not None:
            require_exact_date(item.period_start, "period_start")
        charge_class(item.charge_type)
        parse_uuid(item.item_id)

    if amount == 0:
        return AllocationResult(
            lines=(),
            allocated_cents=0,
            overpayment_cents=0,
            state=AllocationState.ZERO_PAYMENT,
            postings=(),
            policy_id=CANONICAL_POLICY_ID,
            policy_version=CANONICAL_POLICY_VERSION,
        )

    ordered = sorted(items, key=allocation_sort_key)
    remaining = amount
    lines: list[AllocationLine] = []
    for item in ordered:
        if remaining == 0:
            break
        if item.balance_cents == 0:
            continue
        take = min(remaining, item.balance_cents)
        lines.append(
            AllocationLine(
                item_id=item.item_id,
                invoice_id=item.invoice_id,
                charge_type=item.charge_type.strip().upper(),
                amount_cents=take,
                priority_class=charge_class(item.charge_type),
                policy_id=CANONICAL_POLICY_ID,
                policy_version=CANONICAL_POLICY_VERSION,
            )
        )
        remaining -= take

    allocated = amount - remaining
    if sum(line.amount_cents for line in lines) != allocated:
        raise AllocationError("allocation sum drifted")
    state = AllocationState.OVERPAID if remaining else AllocationState.FULLY_ALLOCATED
    # Remaining cash with unpaid items is impossible: the loop drains cash or items.
    open_after = 0
    consumed: dict[str, int] = {}
    for line in lines:
        consumed[line.item_id] = consumed.get(line.item_id, 0) + line.amount_cents
    for item in items:
        left = item.balance_cents - consumed.get(item.item_id, 0)
        if left < 0:
            raise AllocationError("item over-allocated")
        open_after += left
    if remaining and open_after:
        raise AllocationError("cash left while items remain open")
    return AllocationResult(
        lines=tuple(lines),
        allocated_cents=allocated,
        overpayment_cents=remaining,
        state=state,
        postings=_postings(allocated, remaining),
        policy_id=CANONICAL_POLICY_ID,
        policy_version=CANONICAL_POLICY_VERSION,
    )
