"""Allocation facade contract. Canonical parity, policy lock, no clock."""

from __future__ import annotations

import unittest
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from rental_os.algorithms.allocation import (
    LEGACY_V1_RANK,
    CANONICAL_POLICY_ID,
    AllocationError,
    AllocationState,
    OpenItem,
    allocate_payment,
    charge_class,
)
from rental_os.algorithms.money import MoneyError

from engines.allocation.facade import allocate


def _cid(n: int) -> str:
    return str(uuid.UUID(int=n))


def _charge(n, charge_type, due, balance, *, tenant="tenant-1", period=None, currency="KES", lifecycle="POSTED"):
    return {
        "charge_id": _cid(n),
        "invoice_id": _cid(1000 + n),
        "tenant_id": tenant,
        "charge_type": charge_type,
        "due_date": due,
        "balance_cents": balance,
        "period_start": period,
        "currency": currency,
        "lifecycle": lifecycle,
    }


def _call(items, **overrides):
    payload = {
        "payment_cents": 1_000_000,
        "tenant_id": "tenant-1",
        "currency": "KES",
        "source_id": "payment-source-1",
        "effective_date": date(2026, 3, 1),
        "execution_timestamp_utc": "2026-03-01T00:00:00Z",
        "items": items,
        "policy_id": "CANONICAL_PRIORITY",
        "policy_version": 2,
    }
    payload.update(overrides)
    return allocate(**payload)


class AllocationContractTests(unittest.TestCase):
    def test_canonical_utilities_before_earlier_rent(self):
        self.assertLess(LEGACY_V1_RANK["RENT"], LEGACY_V1_RANK["WATER"])
        self.assertLess(charge_class("WATER"), charge_class("RENT"))
        items = [
            _charge(1, "RENT", date(2026, 1, 1), 1_000_000),
            _charge(2, "WATER", date(2026, 2, 1), 1_000_000),
        ]
        result = _call(items, payment_cents=1_000_000)
        canonical = allocate_payment(
            payment_cents=1_000_000,
            tenant_id="tenant-1",
            currency="KES",
            items=[
                OpenItem(_cid(1), _cid(1001), "tenant-1", "RENT", date(2026, 1, 1), 1_000_000),
                OpenItem(_cid(2), _cid(1002), "tenant-1", "WATER", date(2026, 2, 1), 1_000_000),
            ],
        )
        self.assertEqual(result.lines, canonical.lines)
        self.assertEqual(result.lines[0].charge_type, "WATER")
        self.assertEqual(result.allocated_cents, canonical.allocated_cents)
        self.assertEqual(result.postings, canonical.postings)
        self.assertEqual(result.policy_id, CANONICAL_POLICY_ID)
        self.assertEqual(result.policy_version, 2)
        self.assertEqual(result.state, AllocationState.FULLY_ALLOCATED)

    def test_overpayment_is_2020_not_2030(self):
        result = _call([_charge(1, "RENT", date(2026, 1, 1), 2_500_000)], payment_cents=3_000_000)
        self.assertEqual(result.allocated_cents, 2_500_000)
        self.assertEqual(result.overpayment_cents, 500_000)
        self.assertEqual(result.allocated_cents + result.overpayment_cents, 3_000_000)
        accounts = {(p.account, p.direction, p.amount_cents) for p in result.postings}
        self.assertIn(("2020", "CREDIT", 500_000), accounts)
        self.assertNotIn("2030", {p.account for p in result.postings})

    def test_identity_grid(self):
        items = [
            _charge(1, "WATER", date(2026, 1, 2), 50),
            _charge(2, "RENT", date(2026, 1, 1), 80),
            _charge(3, "PENALTY", date(2026, 1, 3), 20),
        ]
        for payment in (0, 1, 50, 70, 150, 200):
            result = _call(items, payment_cents=payment)
            self.assertEqual(result.allocated_cents + result.overpayment_cents, payment)
            self.assertEqual(sum(line.amount_cents for line in result.lines), result.allocated_cents)
            canonical = allocate_payment(
                payment_cents=payment,
                tenant_id="tenant-1",
                currency="KES",
                items=[
                    OpenItem(_cid(1), _cid(1001), "tenant-1", "WATER", date(2026, 1, 2), 50),
                    OpenItem(_cid(2), _cid(1002), "tenant-1", "RENT", date(2026, 1, 1), 80),
                    OpenItem(_cid(3), _cid(1003), "tenant-1", "PENALTY", date(2026, 1, 3), 20),
                ],
            )
            self.assertEqual(result.lines, canonical.lines)
            self.assertEqual(result.postings, canonical.postings)

    def test_determinism_input_order(self):
        items = [
            _charge(1, "GARBAGE", date(2026, 5, 1), 40),
            _charge(2, "LATE_FEE", date(2026, 4, 1), 40),
        ]
        a = _call(items, payment_cents=50)
        b = _call(list(reversed(items)), payment_cents=50)
        self.assertEqual(a.lines, b.lines)
        self.assertEqual(a.postings, b.postings)
        self.assertEqual(a.lines[0].charge_type, "GARBAGE")

    def test_policy_lock_canonical_and_facade(self):
        with self.assertRaises(TypeError):
            LEGACY_V1_RANK["RENT"] = 1  # type: ignore[index]
        item = OpenItem(_cid(1), _cid(1001), "tenant-1", "RENT", date(2026, 1, 1), 100)
        with self.assertRaises(AllocationError):
            allocate_payment(
                payment_cents=100,
                tenant_id="tenant-1",
                currency="KES",
                items=[item],
                policy_id="LEGACY_V1",
                policy_version=1,
            )
        with self.assertRaises(AllocationError):
            _call([_charge(1, "RENT", date(2026, 1, 1), 100)], policy_id="LEGACY_V1", policy_version=1)
        with self.assertRaises(AllocationError):
            _call([_charge(1, "RENT", date(2026, 1, 1), 100)], policy_version=True)

    def test_datetime_rejected_by_canonical_and_facade(self):
        stamped = datetime(2026, 1, 1, 15, 30)
        item = OpenItem(_cid(1), _cid(1001), "tenant-1", "RENT", stamped, 100)  # type: ignore[arg-type]
        with self.assertRaises(AllocationError):
            allocate_payment(payment_cents=100, tenant_id="tenant-1", currency="KES", items=[item])
        with self.assertRaises(AllocationError):
            _call([_charge(1, "RENT", stamped, 100)])
        with self.assertRaises(AllocationError):
            _call(
                [_charge(1, "RENT", date(2026, 1, 1), 100)],
                effective_date=datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
            )

    def test_timestamp_boundaries(self):
        items = [_charge(1, "RENT", date(2026, 1, 1), 100)]
        accepted = _call(items, payment_cents=100, execution_timestamp_utc="2026-03-01T00:00:00.5+00:00")
        self.assertEqual(accepted.execution_timestamp_utc, "2026-03-01T00:00:00.5+00:00")
        for bad in (
            "2026-03-01T00:00:00",
            "2026-03-01T03:00:00+03:00",
            "2026-03-01T00:00:00z",
            "2026-02-31T00:00:00Z",
            "",
        ):
            with self.assertRaises(AllocationError):
                _call(items, payment_cents=100, execution_timestamp_utc=bad)

    def test_tenant_isolation_and_missing_identity(self):
        with self.assertRaises(AllocationError):
            _call([_charge(1, "RENT", date(2026, 1, 1), 100, tenant="other")], payment_cents=100)
        with self.assertRaises(AllocationError):
            _call([_charge(1, "RENT", date(2026, 1, 1), 100)], payment_cents=100, tenant_id="")
        with self.assertRaises(AllocationError):
            _call([_charge(1, "RENT", date(2026, 1, 1), 100)], payment_cents=100, source_id="  ")
        with self.assertRaises(AllocationError):
            _call([_charge(1, "MYSTERY", date(2026, 1, 1), 100)], payment_cents=100)
        duplicate = _charge(1, "RENT", date(2026, 1, 1), 100)
        with self.assertRaises(AllocationError):
            _call([duplicate, dict(duplicate)], payment_cents=100)
        incomplete = _charge(1, "RENT", date(2026, 1, 1), 100)
        del incomplete["lifecycle"]
        with self.assertRaises(AllocationError):
            _call([incomplete], payment_cents=100)

    def test_money_rejects_float_bool_and_negative(self):
        items = [_charge(1, "RENT", date(2026, 1, 1), 100)]
        with self.assertRaises(MoneyError):
            _call(items, payment_cents=10.5)  # type: ignore[arg-type]
        with self.assertRaises(MoneyError):
            _call(items, payment_cents=True)  # type: ignore[arg-type]
        with self.assertRaises(MoneyError):
            _call(items, payment_cents=-1)
        bad = _charge(1, "RENT", date(2026, 1, 1), 1.0)  # type: ignore[arg-type]
        with self.assertRaises(MoneyError):
            _call([bad], payment_cents=100)

    def test_source_has_no_clock_and_no_formula(self):
        source = Path(__file__).resolve().parents[1].joinpath("facade.py").read_text()
        self.assertNotIn("date.today", source)
        self.assertNotIn("datetime.now", source)
        self.assertNotIn("utcnow", source)
        self.assertNotIn("LEGACY_V1_RANK", source)
        self.assertNotIn("uuid4", source)
        self.assertNotIn("ACCT_PREPAID_RENT", source)
        self.assertNotIn("import django", source)


if __name__ == "__main__":
    unittest.main()
