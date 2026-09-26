"""v2.1.0 engines: delinquency, tariff, deposit. Canonical five are not modified."""

from __future__ import annotations

import random
import unittest
import uuid
from datetime import date, timedelta

from rental_os.algorithms.allocation import OpenItem, allocate_payment
from rental_os.algorithms.delinquency import (
    DELINQUENT,
    GRACE_PERIOD,
    CURRENT,
    DelinquencyError,
    Obligation,
    assess_delinquency,
)
from rental_os.algorithms.deposit import apply_security_deposit
from rental_os.algorithms.tariff import Tariff, TariffBand, TariffError, price_consumption


def _id(n: int) -> str:
    return str(uuid.UUID(int=n))


def _item(n, charge, due, balance):
    return OpenItem(
        item_id=_id(n),
        invoice_id=_id(1000 + n),
        tenant_id="t-1",
        charge_type=charge,
        due_date=due,
        balance_cents=balance,
    )


WATER = Tariff(
    "water-2026",
    (
        TariffBand(10, 100),
        TariffBand(None, 250),
    ),
    fixed_charge_cents=500,
    minimum_charge_cents=1_000,
    effective_from=date(2026, 1, 1),
    effective_to=date(2026, 12, 31),
)
NEXT = Tariff(
    "water-2027",
    (TariffBand(None, 300),),
    fixed_charge_cents=0,
    minimum_charge_cents=0,
    effective_from=date(2027, 1, 1),
    effective_to=date(2027, 12, 31),
)


class DelinquencyTests(unittest.TestCase):
    def test_grace_boundaries_and_leap(self):
        due = date(2026, 1, 5)
        item = Obligation("r1", due, 4_000)
        self.assertEqual(assess_delinquency([item], as_of=date(2026, 1, 5), grace_days=3).status, CURRENT)
        self.assertEqual(assess_delinquency([item], as_of=date(2026, 1, 6), grace_days=3).status, GRACE_PERIOD)
        self.assertEqual(assess_delinquency([item], as_of=date(2026, 1, 8), grace_days=3).status, GRACE_PERIOD)
        late = assess_delinquency([item], as_of=date(2026, 1, 9), grace_days=3)
        self.assertEqual(late.status, DELINQUENT)
        self.assertEqual(late.items[0].days_past_due, 4)
        self.assertEqual(assess_delinquency([item], as_of=date(2026, 1, 6), grace_days=0).status, DELINQUENT)
        leap = Obligation("r2", date(2024, 2, 27), 10)
        self.assertEqual(assess_delinquency([leap], as_of=date(2024, 3, 1), grace_days=3).status, GRACE_PERIOD)
        self.assertEqual(assess_delinquency([leap], as_of=date(2024, 3, 2), grace_days=3).status, DELINQUENT)
        year_end = Obligation("r3", date(2026, 12, 30), 10)
        self.assertEqual(assess_delinquency([year_end], as_of=date(2027, 1, 2), grace_days=3).status, GRACE_PERIOD)
        self.assertEqual(assess_delinquency([year_end], as_of=date(2027, 1, 3), grace_days=3).status, DELINQUENT)

    def test_portfolio_conservation_and_exclusions(self):
        rows = [
            Obligation("open", date(2026, 1, 1), 100),
            Obligation("grace", date(2026, 1, 10), 40),
            Obligation("future", date(2026, 2, 1), 7),
            Obligation("paid", date(2026, 1, 1), 0),
            Obligation("draft", date(2026, 1, 1), 999, lifecycle="DRAFT"),
        ]
        result = assess_delinquency(rows, as_of=date(2026, 1, 12), grace_days=3)
        self.assertEqual(result.status, DELINQUENT)
        self.assertEqual(result.delinquent_cents, 100)
        self.assertEqual(result.grace_cents, 40)
        self.assertEqual(result.current_cents, 7)
        self.assertEqual(
            result.current_cents + result.grace_cents + result.delinquent_cents,
            result.open_cents,
        )
        self.assertEqual(assess_delinquency([], as_of=date(2026, 1, 1), grace_days=0).status, CURRENT)
        with self.assertRaises(DelinquencyError):
            assess_delinquency([rows[0], rows[0]], as_of=date(2026, 1, 12), grace_days=0)
        with self.assertRaises(DelinquencyError):
            assess_delinquency([Obligation("x", date(2026, 1, 1), 1)], as_of=date(2026, 1, 1), grace_days=True)  # type: ignore[arg-type]

    def test_property_buckets(self):
        rng = random.Random(20260923)
        for _ in range(200):
            n = rng.randint(0, 8)
            rows = []
            for i in range(n):
                rows.append(
                    Obligation(
                        f"o{i}",
                        date(2026, 1, 1) + timedelta(days=rng.randint(0, 40)),
                        rng.choice([0, 1, 50, 100]),
                    )
                )
            as_of = date(2026, 1, 1) + timedelta(days=rng.randint(0, 50))
            grace = rng.randint(0, 10)
            result = assess_delinquency(rows, as_of=as_of, grace_days=grace)
            self.assertEqual(
                result.current_cents + result.grace_cents + result.delinquent_cents,
                result.open_cents,
            )
            again = assess_delinquency(list(reversed(rows)), as_of=as_of, grace_days=grace)
            self.assertEqual(result.status, again.status)
            self.assertEqual(result.open_cents, again.open_cents)
            self.assertEqual(result.delinquent_cents, again.delinquent_cents)
            self.assertEqual(result.grace_cents, again.grace_cents)
            self.assertEqual(result.current_cents, again.current_cents)
            self.assertEqual(result, assess_delinquency(rows, as_of=as_of, grace_days=grace))


class TariffTests(unittest.TestCase):
    def test_bands_minimum_and_effective_date(self):
        bill = price_consumption(consumption=12, tariffs=[WATER, NEXT], as_of=date(2026, 6, 1))
        self.assertEqual(bill.energy_cents, 10 * 100 + 2 * 250)
        self.assertEqual(bill.charge_cents, 500 + bill.energy_cents)
        self.assertEqual(bill.tariff_id, "water-2026")
        zero = price_consumption(consumption=0, tariffs=[WATER], as_of=date(2026, 6, 1))
        self.assertEqual(zero.energy_cents, 0)
        self.assertEqual(zero.charge_cents, 1_000)
        nxt = price_consumption(consumption=4, tariffs=[WATER, NEXT], as_of=date(2027, 1, 1))
        self.assertEqual(nxt.tariff_id, "water-2027")
        self.assertEqual(nxt.charge_cents, 1_200)
        with self.assertRaises(TariffError):
            price_consumption(consumption=1, tariffs=[WATER, NEXT], as_of=date(2025, 12, 31))
        overlap = Tariff("overlap", (TariffBand(None, 1),), effective_from=date(2026, 6, 1), effective_to=date(2026, 6, 30))
        with self.assertRaises(TariffError):
            price_consumption(consumption=1, tariffs=[WATER, overlap], as_of=date(2026, 6, 15))
        capped = Tariff("cap", (TariffBand(5, 10),), effective_from=date(2026, 1, 1))
        with self.assertRaises(TariffError):
            price_consumption(consumption=6, tariffs=[capped], as_of=date(2026, 1, 2))
        with self.assertRaises(TariffError):
            price_consumption(consumption=-1, tariffs=[WATER], as_of=date(2026, 1, 2))
        with self.assertRaises(TariffError):
            price_consumption(
                consumption=1,
                tariffs=[Tariff("bad", (TariffBand(5, 1), TariffBand(5, 1)))],
                as_of=date(2026, 1, 1),
            )

    def test_property_units_conserve(self):
        rng = random.Random(7)
        tariff = Tariff("t", (TariffBand(10, 5), TariffBand(25, 9), TariffBand(None, 12)))
        for _ in range(100):
            consumption = rng.randint(0, 80)
            bill = price_consumption(consumption=consumption, tariffs=[tariff], as_of=date(2026, 5, 1))
            self.assertEqual(sum(row.units for row in bill.bands), consumption)
            self.assertEqual(bill.charge_cents, bill.fixed_cents + bill.energy_cents)


class DepositTests(unittest.TestCase):
    def test_water_before_rent_and_refund(self):
        items = [_item(1, "RENT", date(2026, 1, 1), 80), _item(2, "WATER", date(2026, 2, 1), 50)]
        applied = apply_security_deposit(held_cents=120, tenant_id="t-1", currency="KES", items=items)
        self.assertEqual([line.charge_type for line in applied.lines], ["WATER", "RENT"])
        self.assertEqual(applied.applied_cents, 120)
        self.assertEqual(applied.refundable_cents, 0)
        refund = apply_security_deposit(held_cents=200, tenant_id="t-1", currency="KES", items=items)
        self.assertEqual(refund.applied_cents, 130)
        self.assertEqual(refund.refundable_cents, 70)
        self.assertEqual(refund.applied_cents + refund.refundable_cents, 200)
        same = allocate_payment(payment_cents=200, tenant_id="t-1", currency="KES", items=items)
        self.assertEqual(
            [(line.charge_type, line.amount_cents) for line in refund.lines],
            [(line.charge_type, line.amount_cents) for line in same.lines],
        )
        self.assertNotIn("2020", {line.charge_type for line in refund.lines})

    def test_property_conservation(self):
        rng = random.Random(11)
        for _ in range(50):
            items = [
                _item(1, "WATER", date(2026, 1, 2), rng.randint(0, 80)),
                _item(2, "RENT", date(2026, 1, 1), rng.randint(0, 80)),
                _item(3, "PENALTY", date(2026, 1, 1), rng.randint(0, 40)),
            ]
            held = rng.randint(0, 300)
            result = apply_security_deposit(held_cents=held, tenant_id="t-1", currency="KES", items=items)
            self.assertEqual(result.applied_cents + result.refundable_cents, held)
            self.assertEqual(sum(line.amount_cents for line in result.lines), result.applied_cents)
            self.assertLessEqual(result.applied_cents, held)


def build_vectors() -> dict:
    due = Obligation("r1", date(2026, 1, 5), 4_000)
    states = {}
    for iso, grace in (
        ("2026-01-05", 3),
        ("2026-01-06", 3),
        ("2026-01-08", 3),
        ("2026-01-09", 3),
        ("2026-01-06", 0),
    ):
        y, m, d = (int(p) for p in iso.split("-"))
        result = assess_delinquency([due], as_of=date(y, m, d), grace_days=grace)
        states[f"{iso}-g{grace}"] = {
            "status": result.status,
            "days_past_due": result.items[0].days_past_due,
            "delinquent_cents": result.delinquent_cents,
        }
    leap = assess_delinquency(
        [Obligation("r2", date(2024, 2, 27), 10)],
        as_of=date(2024, 3, 1),
        grace_days=3,
    )
    bill = price_consumption(consumption=12, tariffs=[WATER, NEXT], as_of=date(2026, 6, 1))
    zero = price_consumption(consumption=0, tariffs=[WATER], as_of=date(2026, 6, 1))
    items = [_item(1, "RENT", date(2026, 1, 1), 80), _item(2, "WATER", date(2026, 2, 1), 50)]
    refund = apply_security_deposit(held_cents=200, tenant_id="t-1", currency="KES", items=items)
    return {
        "version": "2.1.0",
        "delinquency": states,
        "leap_grace": {"status": leap.status, "days_past_due": leap.items[0].days_past_due},
        "tariff_12": {
            "tariff_id": bill.tariff_id,
            "energy_cents": bill.energy_cents,
            "charge_cents": bill.charge_cents,
        },
        "tariff_zero_minimum": {"charge_cents": zero.charge_cents, "energy_cents": zero.energy_cents},
        "deposit_refund": {
            "applied_cents": refund.applied_cents,
            "refundable_cents": refund.refundable_cents,
            "lines": [line.charge_type for line in refund.lines],
            "amounts": [line.amount_cents for line in refund.lines],
        },
    }


if __name__ == "__main__":
    unittest.main()
