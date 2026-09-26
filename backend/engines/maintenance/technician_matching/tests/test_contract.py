"""Matching facade contract. Greedy counterexample must not win."""

from __future__ import annotations

import unittest
from pathlib import Path

from rental_os.algorithms.matching import Job, MatchingError, Technician, match_jobs, rank_technicians

from engines.maintenance.technician_matching.facade import match


class MatchingContractTests(unittest.TestCase):
    def test_greedy_counterexample(self):
        t1 = Technician("t1", ("PLUMBING", "ELECTRICAL"), 5_000, 1_000)
        t2 = Technician("t2", ("PLUMBING",), 5_000, 1_000)
        job_a = Job("A", ("PLUMBING",), (("t1", 0), ("t2", 2_000)))
        job_b = Job("B", ("ELECTRICAL",), (("t1", 0), ("t2", 0)))
        result = match(jobs=[job_a, job_b], technicians=[t1, t2])
        canonical = match_jobs([job_a, job_b], [t1, t2])
        self.assertEqual(result, canonical)
        pairs = {row.job_id: row.technician_id for row in result.assignments}
        self.assertEqual(pairs["A"], "t2")
        self.assertEqual(pairs["B"], "t1")
        self.assertEqual(result.unmatched_job_ids, ())
        solo = rank_technicians(job_a, [t1, t2])
        self.assertEqual(solo[0].technician_id, "t1")
        self.assertNotEqual(pairs["A"], solo[0].technician_id)

    def test_weight_beats_cheaper_index(self):
        jobs = [
            Job("j0", ("S",), (("t0", 5000), ("t1", 0))),
            Job("j1", ("S",), (("t0", 0), ("t1", 5000))),
        ]
        techs = [Technician(f"t{i}", ("S",), 5_000, 1_000) for i in range(2)]
        result = match(jobs=jobs, technicians=techs)
        self.assertEqual(
            [(row.job_id, row.technician_id) for row in result.assignments],
            [("j0", "t1"), ("j1", "t0")],
        )
        self.assertEqual(result, match_jobs(jobs, techs))

    def test_infeasible_and_partial_skill(self):
        none = match(jobs=[Job("J", ("PLUMBING",), ())], technicians=[])
        self.assertEqual(none.assignments, ())
        self.assertEqual(none.unmatched_job_ids, ("J",))
        tech = Technician("t", ("PLUMBING",), 5_000, 1_000)
        partial = match(jobs=[Job("J", ("PLUMBING", "ELECTRICAL"), (("t", 0),))], technicians=[tech])
        self.assertEqual(partial.unmatched_job_ids, ("J",))
        self.assertEqual(partial.assignments, ())

    def test_valid_assignment_tie_and_determinism(self):
        techs = [Technician(f"t{i}", ("S",), 5_000, 1_000) for i in range(3)]
        jobs = [Job(f"j{i}", ("S",), tuple((f"t{j}", 0) for j in range(3))) for i in range(3)]
        result = match(jobs=jobs, technicians=list(reversed(techs)))
        again = match(jobs=list(reversed(jobs)), technicians=techs)
        self.assertEqual(result, again)
        self.assertEqual(
            [(row.job_id, row.technician_id) for row in result.assignments],
            [("j0", "t0"), ("j1", "t1"), ("j2", "t2")],
        )

    def test_boundaries(self):
        zero = match(
            jobs=[Job("J", ("S",), (("t", 1_000_000),))],
            technicians=[Technician("t", ("S",), 0, 0)],
        )
        self.assertEqual(zero.assignments[0].weight_micro, 0)
        self.assertEqual(zero.unmatched_job_ids, ())
        with self.assertRaises(MatchingError):
            match(
                jobs=[Job("J", ("S",), ())],
                technicians=[Technician("t", ("S",), 1_000, 1_000)],
            )
        with self.assertRaises(MatchingError):
            match(
                jobs=[Job("J", ("S",), (("t", 1), ("t", 9)))],
                technicians=[Technician("t", ("S",), 1_000, 1_000)],
            )
        with self.assertRaises(MatchingError):
            match(jobs=[Job("", ("S",), ())], technicians=[])
        with self.assertRaises(MatchingError):
            match(
                jobs=[Job("J", ("S",), (("t", 1.5),))],  # type: ignore[arg-type]
                technicians=[Technician("t", ("S",), 1_000, 1_000)],
            )
        with self.assertRaises(MatchingError):
            match(
                jobs=[Job("J", ("S",), (("t", True),))],  # type: ignore[arg-type]
                technicians=[Technician("t", ("S",), 1_000, 1_000)],
            )

    def test_source_is_not_a_greedy_sort(self):
        source = Path(__file__).resolve().parents[1].joinpath("facade.py").read_text()
        self.assertNotIn("rank_technicians", source)
        self.assertNotIn("sorted", source)
        self.assertNotIn("edge_weight_micro", source)
        self.assertNotIn("date.today", source)
        self.assertNotIn("import django", source)


if __name__ == "__main__":
    unittest.main()
