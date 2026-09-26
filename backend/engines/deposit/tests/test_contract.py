"""Deposit facade contract. 200/50/80 vector. No 2020 posting."""

from __future__ import annotations

import unittest
import uuid
from datetime import date, datetime
from pathlib import Path

from rental_os.algorithms.allocation import AllocationError
from rental_os.algorithms.deposit import apply_security_deposit
from rental_os.algorithms.allocation import OpenItem
from rental_os.algorithms.money import MoneyError

from engines.deposit.facade import apply_deposit


def _cid(n: int) -> str:
    return str(uuid.UUID(int=n))


def _charge(n, charge_type, due, balance):
    return {
        "charge_id": _cid(n),
        "invoice_id": _cid(1000 + n),
        "tenant_id": "tenant-1",
        "charge_type": charge_type,
        "due_date": due,
        "balance_cents": balance,
        "period_start": None,
        "currency": "KES",
        "lifecycle": "POSTED",
    }


def _call(items, held=200):
    return apply_deposit(
        held_cents=held,
        tenant_id="tenant-1",
        currency="KES",
        source_id="deposit-source-1",
        effective_date=date(2026, 3, 1),
        execution_timestamp_utc="2026-03-01T00:00:00Z",
        items=items,
        policy_id="CANONICAL_PRIORITY",
        policy_version=2,
    )


class DepositContractTests(unittest.TestCase):
    def test_published_vector_200_water_50_rent_80(self):
        items = [
            _charge(1, "RENT", date(2026, 1, 1), 80),
            _charge(2, "WATER", date(2026, 2, 1), 50),
        ]
        result = _call(items, 200)
        canonical = apply_security_deposit(
            held_cents=200,
            tenant_id="tenant-1",
            currency="KES",
            items=[
                OpenItem(_cid(1), _cid(1001), "tenant-1", "RENT", date(2026, 1, 1), 80),
                OpenItem(_cid(2), _cid(1002), "tenant-1", "WATER", date(2026, 2, 1), 50),
            ],
        )
        self.assertEqual(result.lines, canonical.lines)
        self.assertEqual([line.charge_type for line in result.lines], ["WATER", "RENT"])
        self.assertEqual([line.amount_cents for line in result.lines], [50, 80])
        self.assertEqual(result.applied_cents, 130)
        self.assertEqual(result.refundable_cents, 70)
        self.assertEqual(result.applied_cents + result.refundable_cents, 200)
        self.assertEqual(result.postings, ())
        self.assertNotIn("2020", {line.charge_type for line in result.lines})
        self.assertEqual(result.policy_version, 2)

    def test_exact_cover_has_zero_refund(self):
        items = [
            _charge(1, "RENT", date(2026, 1, 1), 80),
            _charge(2, "WATER", date(2026, 2, 1), 50),
        ]
        result = _call(items, 130)
        self.assertEqual(result.applied_cents, 130)
        self.assertEqual(result.refundable_cents, 0)
        self.assertEqual(result.postings, ())

    def test_determinism(self):
        items = [
            _charge(1, "RENT", date(2026, 1, 1), 80),
            _charge(2, "WATER", date(2026, 2, 1), 50),
        ]
        a = _call(items, 200)
        b = _call(list(reversed(items)), 200)
        self.assertEqual(a.lines, b.lines)
        self.assertEqual(a.applied_cents, b.applied_cents)
        self.assertEqual(a.refundable_cents, b.refundable_cents)

    def test_policy_tenant_time_and_money(self):
        items = [_charge(1, "WATER", date(2026, 1, 1), 50)]
        with self.assertRaises(AllocationError):
            apply_deposit(
                held_cents=50,
                tenant_id="tenant-1",
                currency="KES",
                source_id="deposit-source-1",
                effective_date=date(2026, 3, 1),
                execution_timestamp_utc="2026-03-01T00:00:00Z",
                items=items,
                policy_id="LEGACY_V1",
                policy_version=1,
            )
        with self.assertRaises(AllocationError):
            apply_deposit(
                held_cents=50,
                tenant_id="other",
                currency="KES",
                source_id="deposit-source-1",
                effective_date=date(2026, 3, 1),
                execution_timestamp_utc="2026-03-01T00:00:00Z",
                items=items,
                policy_id="CANONICAL_PRIORITY",
                policy_version=2,
            )
        with self.assertRaises(AllocationError):
            apply_deposit(
                held_cents=50,
                tenant_id="tenant-1",
                currency="KES",
                source_id="deposit-source-1",
                effective_date=datetime(2026, 3, 1, 0, 0),
                execution_timestamp_utc="2026-03-01T00:00:00Z",
                items=items,
                policy_id="CANONICAL_PRIORITY",
                policy_version=2,
            )
        with self.assertRaises(MoneyError):
            _call(items, 10.0)  # type: ignore[arg-type]
        with self.assertRaises(MoneyError):
            _call(items, True)  # type: ignore[arg-type]
        with self.assertRaises(AllocationError):
            apply_deposit(
                held_cents=50,
                tenant_id="tenant-1",
                currency="KES",
                source_id="",
                effective_date=date(2026, 3, 1),
                execution_timestamp_utc="2026-03-01T00:00:00Z",
                items=items,
                policy_id="CANONICAL_PRIORITY",
                policy_version=2,
            )

    def test_source_does_not_post_or_reimplement(self):
        source = Path(__file__).resolve().parents[1].joinpath("facade.py").read_text()
        self.assertNotIn("Posting(", source)
        self.assertNotIn("ACCT_PREPAID_RENT", source)
        self.assertNotIn("date.today", source)
        self.assertNotIn("datetime.now", source)
        self.assertNotIn("allocate_payment", source)
        self.assertNotIn("import django", source)


if __name__ == "__main__":
    unittest.main()
