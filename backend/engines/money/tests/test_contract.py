import unittest

from engines.money import MoneyError, require_cents, round_half_up_div


class MoneyContractTests(unittest.TestCase):
    def test_integer_cents_and_zero_policy(self):
        self.assertEqual(require_cents(0, name="amount"), 0)
        self.assertEqual(require_cents(123, name="amount"), 123)
        with self.assertRaises(MoneyError):
            require_cents(0, name="amount", allow_zero=False)

    def test_rejects_boolean_float_and_negative_values(self):
        for value in (True, 1.5, -1):
            with self.subTest(value=value), self.assertRaises(MoneyError):
                require_cents(value, name="amount")

    def test_rounds_half_up_without_float(self):
        self.assertEqual(round_half_up_div(1, 2), 1)
        self.assertEqual(round_half_up_div(3, 2), 2)
        self.assertEqual(round_half_up_div(4, 3), 1)
        with self.assertRaises(MoneyError):
            round_half_up_div(1, 0)


if __name__ == "__main__":
    unittest.main()
