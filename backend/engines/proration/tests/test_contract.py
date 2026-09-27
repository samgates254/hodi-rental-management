import unittest
from datetime import date, datetime

from engines.proration import ProrationError, prorate_move_in
from rental_os.algorithms.proration import prorate_move_in as canonical_prorate_move_in


class ProrationContractTests(unittest.TestCase):
    def test_facade_delegates_and_preserves_inclusive_move_in_result(self):
        for rent, move_in in (
            (2_000_000, date(2026, 9, 1)),
            (1_000_000, date(2026, 7, 31)),
            (15, date(2026, 9, 30)),
        ):
            with self.subTest(rent=rent, move_in=move_in):
                self.assertEqual(
                    prorate_move_in(rent, move_in),
                    canonical_prorate_move_in(rent, move_in),
                )

    def test_rejects_datetime_and_invalid_money(self):
        with self.assertRaises(ProrationError):
            prorate_move_in(100, datetime(2026, 1, 1))  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            prorate_move_in(-1, date(2026, 1, 1))
        with self.assertRaises(ValueError):
            prorate_move_in(True, date(2026, 1, 1))  # type: ignore[arg-type]

    def test_repeated_input_is_deterministic(self):
        arguments = (1_234_567, date(2026, 1, 17))
        self.assertEqual(prorate_move_in(*arguments), prorate_move_in(*arguments))


if __name__ == "__main__":
    unittest.main()
