"""Allocation boundary. Validates, delegates, returns the canonical result.

No ranking, no posting construction, no clock, no identifier synthesis.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from rental_os.algorithms.allocation import (
    CANONICAL_POLICY_ID,
    CANONICAL_POLICY_VERSION,
    AllocationError,
    AllocationLine,
    AllocationState,
    OpenItem,
    Posting,
    allocate_payment,
    assert_production_policy,
    require_exact_date,
)
from rental_os.algorithms.money import MoneyError, require_cents


_CHARGE_FIELDS = (
    "charge_id",
    "invoice_id",
    "tenant_id",
    "charge_type",
    "due_date",
    "balance_cents",
    "period_start",
    "currency",
    "lifecycle",
)
_UTC_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$"
)


@dataclass(frozen=True)
class AllocationCharge:
    charge_id: str
    invoice_id: str
    tenant_id: str
    charge_type: str
    due_date: date
    balance_cents: int
    period_start: date | None
    currency: str
    lifecycle: str


@dataclass(frozen=True)
class AllocationFacadeResult:
    source_id: str
    tenant_id: str
    effective_date: date
    execution_timestamp_utc: str
    currency: str
    policy_id: str
    policy_version: int
    lines: tuple[AllocationLine, ...]
    allocated_cents: int
    overpayment_cents: int
    state: AllocationState
    postings: tuple[Posting, ...]


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise AllocationError(f"{name} is required")
    return value


def _require_utc_timestamp(value: object) -> str:
    if not isinstance(value, str) or _UTC_TIMESTAMP.fullmatch(value) is None:
        raise AllocationError("execution_timestamp_utc must be explicit ISO-8601 UTC")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    if "." in text:
        head, tail = text.split(".", 1)
        fraction, offset = tail.split("+", 1)
        text = f"{head}.{(fraction + '000000')[:6]}+{offset}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise AllocationError("execution_timestamp_utc must be explicit ISO-8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise AllocationError("execution_timestamp_utc must be explicit UTC")
    return value


def _charge_mapping(value: AllocationCharge | Mapping[str, object]) -> Mapping[str, object]:
    if isinstance(value, AllocationCharge):
        return {name: getattr(value, name) for name in _CHARGE_FIELDS}
    if isinstance(value, Mapping):
        missing = [name for name in _CHARGE_FIELDS if name not in value]
        extra = sorted(set(value) - set(_CHARGE_FIELDS))
        if missing or extra:
            raise AllocationError(f"charge fields invalid missing={missing} extra={extra}")
        return value
    raise AllocationError("charge must be AllocationCharge or a complete mapping")


def _open_item(value: AllocationCharge | Mapping[str, object], settlement_tenant: str) -> OpenItem:
    data = _charge_mapping(value)
    charge_id = _require_text(data["charge_id"], "charge_id")
    invoice_id = _require_text(data["invoice_id"], "invoice_id")
    tenant_id = _require_text(data["tenant_id"], "tenant_id")
    charge_type = _require_text(data["charge_type"], "charge_type")
    if tenant_id != settlement_tenant:
        raise AllocationError("tenant isolation: item tenant does not match payment")
    due_date = require_exact_date(data["due_date"], "due_date")
    period_start = data["period_start"]
    if period_start is not None:
        period_start = require_exact_date(period_start, "period_start")
    balance = data["balance_cents"]
    if isinstance(balance, bool) or not isinstance(balance, int):
        raise MoneyError(f"balance_cents must be an int number of cents, got {type(balance).__name__}")
    currency = _require_text(data["currency"], "currency")
    lifecycle = _require_text(data["lifecycle"], "lifecycle")
    return OpenItem(
        item_id=charge_id,
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        charge_type=charge_type,
        due_date=due_date,
        balance_cents=balance,
        period_start=period_start,
        currency=currency,
        lifecycle=lifecycle,
    )


def allocate(
    *,
    payment_cents: int,
    tenant_id: str,
    currency: str,
    source_id: str,
    effective_date: date,
    execution_timestamp_utc: str,
    items: list[AllocationCharge | Mapping[str, object]] | tuple[AllocationCharge | Mapping[str, object], ...],
    policy_id: str,
    policy_version: int,
) -> AllocationFacadeResult:
    """Validate the settlement boundary and return allocate_payment's result."""
    assert_production_policy(policy_id, policy_version)
    settlement_tenant = _require_text(tenant_id, "tenant_id")
    source = _require_text(source_id, "source_id")
    settlement_currency = _require_text(currency, "currency")
    effective = require_exact_date(effective_date, "effective_date")
    timestamp = _require_utc_timestamp(execution_timestamp_utc)
    if isinstance(payment_cents, bool) or not isinstance(payment_cents, int):
        raise MoneyError(f"payment_cents must be an int number of cents, got {type(payment_cents).__name__}")
    require_cents(payment_cents, name="payment_cents")
    if not isinstance(items, (list, tuple)):
        raise AllocationError("items must be a list or tuple")
    opened = tuple(_open_item(item, settlement_tenant) for item in items)
    result = allocate_payment(
        payment_cents=payment_cents,
        tenant_id=settlement_tenant,
        currency=settlement_currency,
        items=opened,
        policy_id=CANONICAL_POLICY_ID,
        policy_version=CANONICAL_POLICY_VERSION,
    )
    if result.policy_id != CANONICAL_POLICY_ID or result.policy_version != CANONICAL_POLICY_VERSION:
        raise AllocationError("canonical result was not policy version 2")
    if result.allocated_cents + result.overpayment_cents != payment_cents:
        raise AllocationError("canonical conservation failed at the facade boundary")
    for posting in result.postings:
        if posting.account == "2030":
            raise AllocationError("overpayment must not post to 2030")
    return AllocationFacadeResult(
        source_id=source,
        tenant_id=settlement_tenant,
        effective_date=effective,
        execution_timestamp_utc=timestamp,
        currency=settlement_currency,
        policy_id=result.policy_id,
        policy_version=result.policy_version,
        lines=result.lines,
        allocated_cents=result.allocated_cents,
        overpayment_cents=result.overpayment_cents,
        state=result.state,
        postings=result.postings,
    )
