"""Meter facade contract. Validation only. Canonical rollover."""

from __future__ import annotations

import unittest
from pathlib import Path

from rental_os.algorithms.meter import MeterError, MeterHistoryError, MeterStatus, validate_meter_reading

from engines.meter.facade import validate


class MeterContractTests(unittest.TestCase):
    def test_rollover_9999_to_0001(self):
        result = validate(captured=1, history=[9999])
        canonical = validate_meter_reading(1, [9999])
        self.assertEqual(result, canonical)
        self.assertEqual(result.status, MeterStatus.VALID)
        self.assertTrue(result.rollover)
        self.assertEqual(result.consumption, 2)

    def test_negative_delta_is_tamper(self):
        result = validate(captured=4990, history=[5000])
        self.assertEqual(result.status, MeterStatus.TAMPERED_NEGATIVE)
        self.assertIsNone(result.consumption)
        self.assertFalse(result.rollover)

    def test_valid_increment_and_leak(self):
        valid = validate(captured=130, history=[100, 110, 120])
        self.assertEqual(valid.status, MeterStatus.VALID)
        self.assertEqual(valid.consumption, 10)
        leak = validate(captured=200, history=[100, 110, 120])
        self.assertEqual(leak.status, MeterStatus.SUSPECT_LEAK)
        self.assertEqual(leak.consumption, 80)
        self.assertEqual(leak.baseline, 10)

    def test_quarter_dial_rollover_boundary(self):
        accepted = validate(captured=0, history=[7500])
        self.assertEqual(accepted.status, MeterStatus.VALID)
        self.assertTrue(accepted.rollover)
        self.assertEqual(accepted.consumption, 2500)
        rejected = validate(captured=1, history=[7500])
        self.assertEqual(rejected.status, MeterStatus.TAMPERED_NEGATIVE)
        self.assertEqual(accepted, validate_meter_reading(0, [7500]))

    def test_empty_history_and_exact_three_times(self):
        empty = validate(captured=10, history=[])
        self.assertEqual(empty.status, MeterStatus.VALID)
        self.assertIsNone(empty.consumption)
        exact = validate(captured=150, history=[100, 110, 120])
        self.assertEqual(exact.status, MeterStatus.VALID)
        self.assertEqual(exact.consumption, 30)
        over = validate(captured=151, history=[100, 110, 120])
        self.assertEqual(over.status, MeterStatus.SUSPECT_LEAK)

    def test_determinism_and_invalid(self):
        self.assertEqual(validate(captured=1, history=[9999]), validate(captured=1, history=(9999,)))
        with self.assertRaises(MeterError):
            validate(captured=-1, history=[0])
        with self.assertRaises(MeterError):
            validate(captured=10_000, history=[0])
        with self.assertRaises(MeterError):
            validate(captured=1.0, history=[0])  # type: ignore[arg-type]
        with self.assertRaises(MeterError):
            validate(captured=True, history=[0])  # type: ignore[arg-type]
        with self.assertRaises(MeterHistoryError):
            validate(captured=10, history=[5000, 4990, 5000])
        with self.assertRaises(MeterError):
            validate(captured=1, history=[0], leak_factor_millis=True)  # type: ignore[arg-type]

    def test_source_does_not_price(self):
        source = Path(__file__).resolve().parents[1].joinpath("facade.py").read_text()
        self.assertNotIn("price_consumption", source)
        self.assertNotIn("cents", source)
        self.assertNotIn("date.today", source)
        self.assertNotIn("import django", source)


if __name__ == "__main__":
    unittest.main()
