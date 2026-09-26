"""Priority facade contract. Published vectors and symmetric ties."""

from __future__ import annotations

import unittest
from pathlib import Path

from rental_os.algorithms.priority import HazardBand, PriorityError, score_priority

from engines.maintenance.priority.facade import score


class PriorityContractTests(unittest.TestCase):
    def test_emergency_override(self):
        result = score(hazard=HazardBand.EMERGENCY, vulnerability=1, building_age_years=0, age_band_value=None)
        canonical = score_priority(HazardBand.EMERGENCY, 1, 0)
        self.assertEqual(result, canonical)
        self.assertEqual(result.priority_class, 1)
        self.assertTrue(result.emergency_override)
        self.assertEqual(result.rounded_score, 3)
        self.assertEqual(result.age_band, 1)

    def test_formula_edges_and_half_up(self):
        quiet = score(hazard=HazardBand.INFORMATIONAL, vulnerability=1, building_age_years=None, age_band_value=1)
        self.assertEqual(quiet, score_priority(HazardBand.INFORMATIONAL, 1, age_band_value=1))
        self.assertEqual(quiet.score_millis, 1000)
        self.assertEqual(quiet.priority_class, 5)
        severe = score(hazard=HazardBand.HIGH, vulnerability=5, building_age_years=None, age_band_value=5)
        self.assertEqual(severe.rounded_score, 5)
        self.assertEqual(severe.priority_class, 1)
        half = score(hazard=HazardBand.INFORMATIONAL, vulnerability=1, building_age_years=16, age_band_value=None)
        self.assertEqual(half.score_millis, 1500)
        self.assertEqual(half.rounded_score, 2)
        self.assertEqual(half.priority_class, 4)
        self.assertFalse(half.emergency_override)

    def test_age_band_boundaries(self):
        expected = {0: 1, 5: 1, 6: 2, 15: 2, 16: 3, 30: 3, 31: 4, 50: 4, 51: 5}
        for years, band in expected.items():
            result = score(hazard=1, vulnerability=1, building_age_years=years, age_band_value=None)
            self.assertEqual(result.age_band, band)
            self.assertEqual(result, score_priority(1, 1, years))

    def test_symmetric_inputs_tie(self):
        left = score(hazard=2, vulnerability=1, building_age_years=None, age_band_value=5)
        right = score(hazard=2, vulnerability=5, building_age_years=None, age_band_value=1)
        self.assertEqual(left.score_millis, right.score_millis)
        self.assertEqual(left.rounded_score, right.rounded_score)
        self.assertEqual(left.priority_class, right.priority_class)
        again = score(hazard=2, vulnerability=1, building_age_years=None, age_band_value=5)
        self.assertEqual(left, again)

    def test_invalid(self):
        with self.assertRaises(PriorityError):
            score(hazard=True, vulnerability=1, building_age_years=0, age_band_value=None)  # type: ignore[arg-type]
        with self.assertRaises(PriorityError):
            score(hazard=5.9, vulnerability=1, building_age_years=0, age_band_value=None)  # type: ignore[arg-type]
        with self.assertRaises(PriorityError):
            score(hazard=HazardBand.LOW, vulnerability=0, building_age_years=10, age_band_value=None)
        with self.assertRaises(PriorityError):
            score(hazard=HazardBand.LOW, vulnerability=3, building_age_years=-1, age_band_value=None)
        with self.assertRaises(PriorityError):
            score(hazard=HazardBand.LOW, vulnerability=3, building_age_years=10, age_band_value=2)
        with self.assertRaises(PriorityError):
            score(hazard=HazardBand.LOW, vulnerability=3, building_age_years=None, age_band_value=None)

    def test_source_does_not_score(self):
        source = Path(__file__).resolve().parents[1].joinpath("facade.py").read_text()
        self.assertNotIn("score_millis", source)
        self.assertNotIn("date.today", source)
        self.assertNotIn("import django", source)


if __name__ == "__main__":
    unittest.main()
