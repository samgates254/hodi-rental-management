"""Deposit boundary. Delegates to apply_security_deposit.

Refundable cents are not posted. This module does not build journals and
does not send a remainder to account 2020.
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
    OpenItem,
    assert_production_policy,
    require_exact_date,
)
from rental_os.algorithms.deposit import apply_security_deposit
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
class DepositCharge:
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
class DepositFacadeResult:
    source_id: str
    tenant_id: str
    effective_date: date
    execution_timestamp_utc: str
    currency: str
    applied_cents: int
    refundable_cents: int
    lines: tuple[AllocationLine, ...]
    policy_id: str
    policy_version: int
    postings: tuple[()]


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


def _charge_mapping(value: DepositCharge | Mapping[str, object]) -> Mapping[str, object]:
    if isinstance(value, DepositCharge):
        return {name: getattr(value, name) for name in _CHARGE_FIELDS}
    if isinstance(value, Mapping):
        missing = [name for name in _CHARGE_FIELDS if name not in value]
        extra = sorted(set(value) - set(_CHARGE_FIELDS))
        if missing or extra:
            raise AllocationError(f"charge fields invalid missing={missing} extra={extra}")
        return value
    raise AllocationError("charge must be DepositCharge or a complete mapping")


def _open_item(value: DepositCharge | Mapping[str, object], settlement_tenant: str) -> OpenItem:
    data = _charge_mapping(value)
    tenant_id = _require_text(data["tenant_id"], "tenant_id")
    if tenant_id != settlement_tenant:
        raise AllocationError("tenant isolation: item tenant does not match deposit")
    period_start = data["period_start"]
    if period_start is not None:
        period_start = require_exact_date(period_start, "period_start")
    balance = data["balance_cents"]
    if isinstance(balance, bool) or not isinstance(balance, int):
        raise MoneyError(f"balance_cents must be an int number of cents, got {type(balance).__name__}")
    return OpenItem(
        item_id=_require_text(data["charge_id"], "charge_id"),
        invoice_id=_require_text(data["invoice_id"], "invoice_id"),
        tenant_id=tenant_id,
        charge_type=_require_text(data["charge_type"], "charge_type"),
        due_date=require_exact_date(data["due_date"], "due_date"),
        balance_cents=balance,
        period_start=period_start,
        currency=_require_text(data["currency"], "currency"),
        lifecycle=_require_text(data["lifecycle"], "lifecycle"),
    )


def apply_deposit(
    *,
    held_cents: int,
    tenant_id: str,
    currency: str,
    source_id: str,
    effective_date: date,
    execution_timestamp_utc: str,
    items: list[DepositCharge | Mapping[str, object]] | tuple[DepositCharge | Mapping[str, object], ...],
    policy_id: str,
    policy_version: int,
) -> DepositFacadeResult:
    """Apply a held deposit. postings is always empty."""
    assert_production_policy(policy_id, policy_version)
    settlement_tenant = _require_text(tenant_id, "tenant_id")
    source = _require_text(source_id, "source_id")
    settlement_currency = _require_text(currency, "currency")
    effective = require_exact_date(effective_date, "effective_date")
    timestamp = _require_utc_timestamp(execution_timestamp_utc)
    if isinstance(held_cents, bool) or not isinstance(held_cents, int):
        raise MoneyError(f"held_cents must be an int number of cents, got {type(held_cents).__name__}")
    require_cents(held_cents, name="held_cents")
    if not isinstance(items, (list, tuple)):
        raise AllocationError("items must be a list or tuple")
    opened = tuple(_open_item(item, settlement_tenant) for item in items)
    application = apply_security_deposit(
        held_cents=held_cents,
        tenant_id=settlement_tenant,
        currency=settlement_currency,
        items=opened,
    )
    if application.applied_cents + application.refundable_cents != held_cents:
        raise AllocationError("deposit conservation failed at the facade boundary")
    if application.policy_id != CANONICAL_POLICY_ID or application.policy_version != CANONICAL_POLICY_VERSION:
        raise AllocationError("canonical deposit result was not policy version 2")
    return DepositFacadeResult(
        source_id=source,
        tenant_id=settlement_tenant,
        effective_date=effective,
        execution_timestamp_utc=timestamp,
        currency=settlement_currency,
        applied_cents=application.applied_cents,
        refundable_cents=application.refundable_cents,
        lines=application.lines,
        policy_id=application.policy_id,
        policy_version=application.policy_version,
        postings=(),
    )
