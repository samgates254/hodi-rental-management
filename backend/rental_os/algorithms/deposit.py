"""Apply a held security deposit to open items.

The pay-down order is the canonical allocator. Leftover held cash is
refundable deposit, not prepaid rent 2020. This function does not post
journals. The backend owns the deposit-liability accounts.
"""

from __future__ import annotations

from dataclasses import dataclass

from .allocation import AllocationLine, OpenItem, allocate_payment
from .money import require_cents


@dataclass(frozen=True)
class DepositApplication:
    applied_cents: int
    refundable_cents: int
    lines: tuple[AllocationLine, ...]
    policy_id: str
    policy_version: int


def apply_security_deposit(
    *,
    held_cents: int,
    tenant_id: str,
    currency: str,
    items: list[OpenItem] | tuple[OpenItem, ...],
) -> DepositApplication:
    """Apply held deposit cents. applied + refundable = held.

    Complexity: O(N log N), the same sort as allocation.
    """
    held = require_cents(held_cents, name="held_cents")
    allocation = allocate_payment(
        payment_cents=held,
        tenant_id=tenant_id,
        currency=currency,
        items=items,
    )
    refundable = held - allocation.allocated_cents
    if refundable != allocation.overpayment_cents:
        raise AssertionError("deposit remainder drifted from the allocator")
    if allocation.allocated_cents + refundable != held:
        raise AssertionError("deposit conservation failed")
    return DepositApplication(
        applied_cents=allocation.allocated_cents,
        refundable_cents=refundable,
        lines=allocation.lines,
        policy_id=allocation.policy_id,
        policy_version=allocation.policy_version,
    )
