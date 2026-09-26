"""Tariff facade contract. 12-unit and zero-consumption vectors."""

from __future__ import annotations

import unittest
from datetime import date, datetime
from pathlib import Path

from rental_os.algorithms.money import MoneyError
from rental_os.algorithms.tariff import Tariff, TariffBand, TariffError, price_consumption

from engines.tariff.facade import price


WATER = Tariff(
    "water-2026",
    (TariffBand(10, 100), TariffBand(None, 250)),
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


class TariffContractTests(unittest.TestCase):
    def test_twelve_units_energy_1500_charge_2000(self):
        bill = price(consumption=12, tariffs=[WATER, NEXT], as_of=date(2026, 6, 1))
        canonical = price_consumption(consumption=12, tariffs=[WATER, NEXT], as_of=date(2026, 6, 1))
        self.assertEqual(bill, canonical)
        self.assertEqual(bill.energy_cents, 1_500)
        self.assertEqual(bill.charge_cents, 2_000)
        self.assertEqual(bill.fixed_cents, 500)
        self.assertEqual(bill.tariff_id, "water-2026")
        self.assertEqual(sum(row.units for row in bill.bands), 12)

    def test_zero_consumption_minimum_1000(self):
        bill = price(consumption=0, tariffs=[WATER], as_of=date(2026, 6, 1))
        self.assertEqual(bill.energy_cents, 0)
        self.assertEqual(bill.charge_cents, 1_000)
        self.assertEqual(bill, price_consumption(consumption=0, tariffs=[WATER], as_of=date(2026, 6, 1)))

    def test_determinism_and_rejections(self):
        a = price(consumption=12, tariffs=(NEXT, WATER), as_of=date(2026, 6, 1))
        b = price(consumption=12, tariffs=(WATER, NEXT), as_of=date(2026, 6, 1))
        self.assertEqual(a, b)
        with self.assertRaises(TariffError):
            price(consumption=12.0, tariffs=[WATER], as_of=date(2026, 6, 1))  # type: ignore[arg-type]
        with self.assertRaises(TariffError):
            price(consumption=True, tariffs=[WATER], as_of=date(2026, 6, 1))  # type: ignore[arg-type]
        with self.assertRaises(TariffError):
            price(consumption=1, tariffs=[WATER], as_of=datetime(2026, 6, 1, 0, 0))  # type: ignore[arg-type]
        with self.assertRaises(TariffError):
            price(consumption=-1, tariffs=[WATER], as_of=date(2026, 6, 1))
        with self.assertRaises(TariffError):
            price(consumption=1, tariffs=[], as_of=date(2026, 6, 1))
        capped = Tariff("cap", (TariffBand(5, 10),), effective_from=date(2026, 1, 1))
        with self.assertRaises(TariffError):
            price(consumption=6, tariffs=[capped], as_of=date(2026, 1, 2))
        float_price = Tariff("bad", (TariffBand(None, 1.5),))  # type: ignore[arg-type]
        with self.assertRaises(MoneyError):
            price(consumption=1, tariffs=[float_price], as_of=date(2026, 1, 2))

    def test_source_does_not_validate_meters_or_copy_formula(self):
        source = Path(__file__).resolve().parents[1].joinpath("facade.py").read_text()
        self.assertNotIn("validate_meter", source)
        self.assertNotIn("date.today", source)
        self.assertNotIn("datetime.now", source)
        self.assertNotIn("import django", source)
        self.assertNotIn(" * ", source)


if __name__ == "__main__":
    unittest.main()
