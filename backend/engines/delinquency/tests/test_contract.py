"""Published delinquency boundaries through the facade."""

from __future__ import annotations

import unittest
from datetime import date, datetime
from pathlib import Path

from rental_os.algorithms.delinquency import DelinquencyError, Obligation, assess_delinquency
from rental_os.algorithms.money import MoneyError

from engines.delinquency.facade import assess


def _row(obligation_id, due, balance, lifecycle="POSTED"):
    return {
        "obligation_id": obligation_id,
        "due_date": due,
        "balance_cents": balance,
        "lifecycle": lifecycle,
    }


class DelinquencyContractTests(unittest.TestCase):
    def test_published_boundaries(self):
        due = date(2026, 1, 5)
        row = [_row("r1", due, 4_000)]
        expected = {
            date(2026, 1, 5): ("CURRENT", 0, 0, 3),
            date(2026, 1, 6): ("GRACE_PERIOD", 1, 0, 3),
            date(2026, 1, 8): ("GRACE_PERIOD", 3, 0, 3),
            date(2026, 1, 9): ("DELINQUENT", 4, 4_000, 3),
        }
        for as_of, (status, days, delinquent, grace) in expected.items():
            result = assess(obligations=row, as_of=as_of, grace_days=grace)
            canonical = assess_delinquency(
                [Obligation("r1", due, 4_000)],
                as_of=as_of,
                grace_days=grace,
            )
            self.assertEqual(result, canonical)
            self.assertEqual(result.status, status)
            self.assertEqual(result.items[0].days_past_due, days)
            self.assertEqual(result.delinquent_cents, delinquent)
        zero = assess(obligations=row, as_of=date(2026, 1, 6), grace_days=0)
        self.assertEqual(zero.status, "DELINQUENT")
        self.assertEqual(zero.items[0].days_past_due, 1)
        leap = assess(
            obligations=[_row("r2", date(2024, 2, 27), 10)],
            as_of=date(2024, 3, 1),
            grace_days=3,
        )
        self.assertEqual(leap.status, "GRACE_PERIOD")
        self.assertEqual(leap.items[0].days_past_due, 3)
        after = assess(
            obligations=[_row("r2", date(2024, 2, 27), 10)],
            as_of=date(2024, 3, 2),
            grace_days=3,
        )
        self.assertEqual(after.status, "DELINQUENT")

    def test_determinism_and_conservation(self):
        rows = [
            _row("open", date(2026, 1, 1), 100),
            _row("grace", date(2026, 1, 10), 40),
            _row("future", date(2026, 2, 1), 7),
            _row("paid", date(2026, 1, 1), 0),
            _row("draft", date(2026, 1, 1), 999, lifecycle="DRAFT"),
        ]
        a = assess(obligations=rows, as_of=date(2026, 1, 12), grace_days=3)
        same = assess(obligations=rows, as_of=date(2026, 1, 12), grace_days=3)
        self.assertEqual(a, same)
        reversed_rows = assess(obligations=list(reversed(rows)), as_of=date(2026, 1, 12), grace_days=3)
        self.assertEqual(a.status, reversed_rows.status)
        self.assertEqual(a.open_cents, reversed_rows.open_cents)
        self.assertEqual(a.delinquent_cents, reversed_rows.delinquent_cents)
        self.assertEqual(a.grace_cents, reversed_rows.grace_cents)
        self.assertEqual(a.current_cents, reversed_rows.current_cents)
        self.assertEqual(
            sorted((item.obligation_id, item.status, item.balance_cents) for item in a.items),
            sorted((item.obligation_id, item.status, item.balance_cents) for item in reversed_rows.items),
        )
        self.assertEqual(a.current_cents + a.grace_cents + a.delinquent_cents, a.open_cents)
        self.assertEqual(a.delinquent_cents, 100)
        self.assertEqual(a.grace_cents, 40)
        self.assertEqual(a.current_cents, 7)

    def test_rejects_clock_substitutes_and_bad_money(self):
        row = [_row("r1", date(2026, 1, 5), 4_000)]
        with self.assertRaises(DelinquencyError):
            assess(obligations=row, as_of=datetime(2026, 1, 5, 0, 0), grace_days=3)  # type: ignore[arg-type]
        with self.assertRaises(DelinquencyError):
            assess(obligations=row, as_of=date(2026, 1, 5), grace_days=True)  # type: ignore[arg-type]
        with self.assertRaises(MoneyError):
            assess(obligations=[_row("r1", date(2026, 1, 5), 1.5)], as_of=date(2026, 1, 5), grace_days=3)  # type: ignore[list-item]
        with self.assertRaises(DelinquencyError):
            assess(obligations=[_row("r1", date(2026, 1, 5), 4_000), _row("r1", date(2026, 1, 5), 4_000)], as_of=date(2026, 1, 9), grace_days=3)
        missing = _row("r1", date(2026, 1, 5), 4_000)
        del missing["lifecycle"]
        with self.assertRaises(DelinquencyError):
            assess(obligations=[missing], as_of=date(2026, 1, 5), grace_days=3)

    def test_source_has_no_clock_or_formula(self):
        source = Path(__file__).resolve().parents[1].joinpath("facade.py").read_text()
        self.assertNotIn("date.today", source)
        self.assertNotIn("datetime.now", source)
        self.assertNotIn("timedelta", source)
        self.assertNotIn("import django", source)


if __name__ == "__main__":
    unittest.main()
