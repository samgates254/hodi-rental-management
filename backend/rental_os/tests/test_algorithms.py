"""Regression tests for the canonical Rental OS algorithms."""

from __future__ import annotations

import unittest
import uuid
import calendar
from datetime import date

from rental_os.algorithms.allocation import (
    LEGACY_V1_RANK,
    AllocationError,
    AllocationState,
    OpenItem,
    allocate_payment,
    charge_class,
    parse_uuid,
)
from rental_os.algorithms.matching import (
    Assignment,
    Job,
    MatchingError,
    Technician,
    edge_weight_micro,
    exp_decay_micro,
    match_jobs,
    rank_technicians,
)
from rental_os.algorithms.matching import _hungarian_min
from rental_os.algorithms.meter import (
    MeterError,
    MeterHistoryError,
    MeterStatus,
    validate_meter_reading,
)
from rental_os.algorithms.priority import HazardBand, PriorityError, age_band, score_priority
from rental_os.algorithms.proration import prorate_move_in


def _id(n: int) -> str:
    return str(uuid.UUID(int=n))


def _item(n, charge, due, balance, period=None, tenant="t-1", lifecycle="POSTED"):
    return OpenItem(
        item_id=_id(n),
        invoice_id=_id(1000 + n),
        tenant_id=tenant,
        charge_type=charge,
        due_date=due,
        balance_cents=balance,
        period_start=period,
        lifecycle=lifecycle,
    )


class ProrationTests(unittest.TestCase):
    def test_full_month_identity_30_31_and_leap(self):
        for day0, move in (
            (date(2026, 9, 1), 30),
            (date(2026, 7, 1), 31),
            (date(2024, 2, 1), 29),
            (date(2026, 2, 1), 28),
        ):
            result = prorate_move_in(2_000_000, day0)
            self.assertEqual(result.days_in_month, move)
            self.assertEqual(result.charge_cents, 2_000_000)

    def test_move_in_last_day_of_31(self):
        result = prorate_move_in(1_000_000, date(2026, 7, 31))
        self.assertEqual(result.occupied_days, 1)
        self.assertEqual(result.charge_cents, (1_000_000 + 15) // 31)

    def test_half_month_exact(self):
        result = prorate_move_in(1_000_000, date(2026, 9, 16))
        self.assertEqual(result.occupied_days, 15)
        self.assertEqual(result.charge_cents, 500_000)

    def test_rejects_negative_and_non_int(self):
        with self.assertRaises(Exception):
            prorate_move_in(-1, date(2026, 9, 1))
        with self.assertRaises(Exception):
            prorate_move_in(True, date(2026, 9, 1))  # type: ignore[arg-type]

    def test_repeatable(self):
        a = prorate_move_in(1_234_567, date(2026, 1, 17))
        b = prorate_move_in(1_234_567, date(2026, 1, 17))
        self.assertEqual(a, b)


class AllocationTests(unittest.TestCase):
    def test_utilities_beat_earlier_rent(self):
        """Confirmed defect in financial_mvp v1: RENT rank 10 is before WATER rank 20."""
        self.assertLess(LEGACY_V1_RANK["RENT"], LEGACY_V1_RANK["WATER"])
        self.assertLess(charge_class("WATER"), charge_class("RENT"))
        rent = _item(1, "RENT", date(2026, 1, 1), 1_000_000)
        water = _item(2, "WATER", date(2026, 2, 1), 1_000_000)
        result = allocate_payment(payment_cents=1_000_000, tenant_id="t-1", currency="KES", items=[rent, water])
        self.assertEqual(result.lines[0].charge_type, "WATER")
        self.assertEqual(result.lines[0].amount_cents, 1_000_000)
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.state, AllocationState.FULLY_ALLOCATED)
        self.assertEqual(result.overpayment_cents, 0)

    def test_full_class_order_and_fifo_inside_class(self):
        items = [
            _item(5, "OTHER", date(2026, 1, 1), 10),
            _item(4, "RENT", date(2026, 1, 2), 10),
            _item(3, "PENALTY", date(2026, 1, 3), 10),
            _item(2, "SERVICE_CHARGE", date(2026, 1, 4), 10),
            _item(1, "WATER", date(2026, 3, 1), 10),
            _item(6, "ELECTRICITY", date(2026, 1, 1), 10),
        ]
        result = allocate_payment(payment_cents=60, tenant_id="t-1", currency="KES", items=items)
        self.assertEqual(
            [line.charge_type for line in result.lines],
            ["ELECTRICITY", "WATER", "SERVICE_CHARGE", "PENALTY", "RENT", "OTHER"],
        )
        self.assertEqual(result.overpayment_cents, 0)
        debits = sum(p.amount_cents for p in result.postings if p.direction == "DEBIT")
        credits = sum(p.amount_cents for p in result.postings if p.direction == "CREDIT")
        self.assertEqual(debits, credits)
        self.assertEqual(result.policy_version, 2)

    def test_partial_then_stop_on_cash(self):
        items = [
            _item(1, "WATER", date(2026, 1, 1), 500_000),
            _item(2, "RENT", date(2026, 1, 1), 2_000_000),
        ]
        result = allocate_payment(payment_cents=1_500_000, tenant_id="t-1", currency="KES", items=items)
        self.assertEqual([(l.charge_type, l.amount_cents) for l in result.lines], [("WATER", 500_000), ("RENT", 1_000_000)])
        self.assertEqual(result.state, AllocationState.FULLY_ALLOCATED)
        self.assertEqual(result.overpayment_cents, 0)

    def test_overpayment_posts_to_2020_not_2030(self):
        items = [_item(1, "RENT", date(2026, 1, 1), 2_500_000)]
        result = allocate_payment(payment_cents=3_000_000, tenant_id="t-1", currency="KES", items=items)
        self.assertEqual(result.state, AllocationState.OVERPAID)
        self.assertEqual(result.allocated_cents, 2_500_000)
        self.assertEqual(result.overpayment_cents, 500_000)
        accounts = {(p.account, p.direction, p.amount_cents) for p in result.postings}
        self.assertIn(("2020", "CREDIT", 500_000), accounts)
        self.assertNotIn("2030", {p.account for p in result.postings})

    def test_no_open_items_is_overpayment(self):
        result = allocate_payment(payment_cents=500, tenant_id="t-1", currency="KES", items=[])
        self.assertEqual(result.state, AllocationState.OVERPAID)
        self.assertEqual(result.lines, ())
        self.assertEqual(result.overpayment_cents, 500)

    def test_zero_payment(self):
        result = allocate_payment(
            payment_cents=0,
            tenant_id="t-1",
            currency="KES",
            items=[_item(1, "RENT", date(2026, 1, 1), 100)],
        )
        self.assertEqual(result.state, AllocationState.ZERO_PAYMENT)

    def test_rejects(self):
        good = _item(1, "RENT", date(2026, 1, 1), 100)
        with self.assertRaises(AllocationError):
            allocate_payment(payment_cents=100, tenant_id="t-1", currency="USD", items=[good])
        with self.assertRaises(AllocationError):
            allocate_payment(payment_cents=100, tenant_id="other", currency="KES", items=[good])
        with self.assertRaises(AllocationError):
            allocate_payment(payment_cents=100, tenant_id="t-1", currency="KES", items=[good, good])
        draft = _item(2, "RENT", date(2026, 1, 1), 100, lifecycle="DRAFT")
        with self.assertRaises(AllocationError):
            allocate_payment(payment_cents=100, tenant_id="t-1", currency="KES", items=[draft])
        with self.assertRaises(AllocationError):
            allocate_payment(payment_cents=100, tenant_id="t-1", currency="KES", items=[_item(3, "MYSTERY", date(2026, 1, 1), 100)])
        with self.assertRaises(Exception):
            allocate_payment(payment_cents=-1, tenant_id="t-1", currency="KES", items=[good])

    def test_uuid_tie_break_is_byte_order(self):
        later = _item(2, "WATER", date(2026, 1, 1), 100)
        earlier = _item(1, "WATER", date(2026, 1, 1), 100)
        result = allocate_payment(payment_cents=100, tenant_id="t-1", currency="KES", items=[later, earlier])
        self.assertEqual(result.lines[0].item_id, _id(1))

    def test_repeatable(self):
        items = [_item(1, "GARBAGE", date(2026, 5, 1), 40), _item(2, "LATE_FEE", date(2026, 4, 1), 40)]
        a = allocate_payment(payment_cents=50, tenant_id="t-1", currency="KES", items=items)
        b = allocate_payment(payment_cents=50, tenant_id="t-1", currency="KES", items=list(reversed(items)))
        self.assertEqual(a, b)
        self.assertEqual(a.lines[0].charge_type, "GARBAGE")


class HungarianTests(unittest.TestCase):
    def test_known_min_cost(self):
        cost = [
            [4, 1, 3],
            [2, 0, 5],
            [3, 2, 2],
        ]
        assigned = _hungarian_min(cost)
        total = sum(cost[i][j] for i, j in enumerate(assigned))
        self.assertEqual(total, 5)
        self.assertEqual(len(set(assigned)), 3)


class MatchingTests(unittest.TestCase):
    @staticmethod
    def _exhaustive_maximum_weight(weights):
        """Independent assignment oracle for small graphs.

        Each row is a job and each column is a technician. ``None`` means an
        ineligible edge. The search explicitly includes an unmatched option,
        rather than using the production Hungarian cost matrix.
        """
        best = (0, 0)

        def search(job_index, used, score, matched):
            nonlocal best
            if job_index == len(weights):
                best = max(best, (score, matched))
                return
            search(job_index + 1, used, score, matched)
            for technician_index, weight in enumerate(weights[job_index]):
                if weight is None or technician_index in used:
                    continue
                used.add(technician_index)
                search(job_index + 1, used, score + weight, matched + 1)
                used.remove(technician_index)

        search(0, set(), 0, 0)
        return best

    def test_exp_zero_and_known_range(self):
        self.assertEqual(exp_decay_micro(0), 1_000_000)
        # exp(-1) ≈ 0.367879
        self.assertEqual(exp_decay_micro(5000), 367_879)

    def test_greedy_failure_is_not_optimal(self):
        """T1 is best for both; only T1 can do electrical. Optimal gives T1 to B."""
        t1 = Technician("t1", ("PLUMBING", "ELECTRICAL"), 5_000, 1_000)
        t2 = Technician("t2", ("PLUMBING",), 5_000, 1_000)
        job_a = Job("A", ("PLUMBING",), (("t1", 0), ("t2", 2_000)))
        job_b = Job("B", ("ELECTRICAL",), (("t1", 0), ("t2", 0)))
        result = match_jobs([job_a, job_b], [t1, t2])
        pairs = {a.job_id: a.technician_id for a in result.assignments}
        self.assertEqual(pairs["A"], "t2")
        self.assertEqual(pairs["B"], "t1")
        self.assertEqual(result.unmatched_job_ids, ())
        # Greedy on A alone would have taken t1.
        solo = rank_technicians(job_a, [t1, t2])
        self.assertEqual(solo[0].technician_id, "t1")

    def test_scoreless_edge_does_not_displace_positive_edge(self):
        """Regression: old dummy costs maximized cardinality before score."""
        t1 = Technician("t1", ("A", "B"), 0, 0)
        t2 = Technician("t2", ("A",), 0, 0)
        job_a = Job("A", ("A",), (("t1", 0), ("t2", 75_000)))
        job_b = Job("B", ("B",), (("t1", 75_000), ("t2", 75_000)))

        result = match_jobs([job_a, job_b], [t1, t2])

        self.assertEqual(
            result.assignments,
            (Assignment("A", "t1", 500_000),),
        )
        self.assertEqual(result.unmatched_job_ids, ("B",))

    def test_small_graphs_match_independent_exhaustive_oracle(self):
        technicians = [
            Technician("t1", ("S",), 0, 0),
            Technician("t2", ("S",), 0, 0),
            Technician("t3", ("S",), 0, 0),
        ]
        jobs = [
            Job("A", ("S",), (("t1", 0), ("t2", 75_000), ("t3", 10_000))),
            Job("B", ("S",), (("t1", 75_000), ("t2", 0), ("t3", 75_000))),
            Job("C", ("S",), (("t1", 10_000), ("t2", 75_000), ("t3", 75_000))),
        ]
        weights = [
            [
                edge_weight_micro(
                    distance_m=dict(job.distance_m_by_technician)[technician.technician_id],
                    rating_milli=technician.rating_milli,
                    acceptance_milli=technician.acceptance_milli,
                )
                for technician in technicians
            ]
            for job in jobs
        ]

        result = match_jobs(jobs, technicians)
        actual = (
            sum(assignment.weight_micro for assignment in result.assignments),
            len(result.assignments),
        )
        self.assertEqual(actual, self._exhaustive_maximum_weight(weights))
        self.assertEqual(len({assignment.technician_id for assignment in result.assignments}), len(result.assignments))
        self.assertEqual(match_jobs(jobs[::-1], technicians[::-1]), result)

    def test_zero_weight_edges_lose_only_to_a_better_score_and_are_repeatable(self):
        technician = Technician("t", ("S",), 0, 0)
        job = Job("J", ("S",), (("t", 75_000),))
        first = match_jobs([job], [technician])
        second = match_jobs([job], [technician])
        self.assertEqual(first, second)
        self.assertEqual(first.assignments, (Assignment("J", "t", 0),))
        self.assertEqual(first.unmatched_job_ids, ())

    def test_tie_lowest_technician_id(self):
        t_b = Technician("b", ("PLUMBING",), 4_000, 800)
        t_a = Technician("a", ("PLUMBING",), 4_000, 800)
        job = Job("J", ("PLUMBING",), (("a", 100), ("b", 100)))
        ranked = rank_technicians(job, [t_b, t_a])
        self.assertEqual(ranked[0].technician_id, "a")
        self.assertEqual(ranked[0].weight_micro, ranked[1].weight_micro)

    def test_unverified_and_skill_and_timeout_skipped(self):
        bad = Technician("bad", ("PLUMBING",), 5_000, 1_000, verified=False)
        wrong = Technician("wrong", ("ELECTRICAL",), 5_000, 1_000)
        used = Technician("used", ("PLUMBING",), 5_000, 1_000)
        ok = Technician("ok", ("PLUMBING",), 1_000, 100)
        job = Job("J", ("PLUMBING",), (("bad", 0), ("wrong", 0), ("used", 0), ("ok", 4_000)), ("used",))
        ranked = rank_technicians(job, [bad, wrong, used, ok])
        self.assertEqual([a.technician_id for a in ranked], ["ok"])

    def test_no_technicians(self):
        result = match_jobs([Job("J", ("PLUMBING",), ())], [])
        self.assertEqual(result.assignments, ())
        self.assertEqual(result.unmatched_job_ids, ("J",))

    def test_partial_skill_does_not_match(self):
        tech = Technician("t", ("PLUMBING",), 5_000, 1_000)
        job = Job("J", ("PLUMBING", "ELECTRICAL"), (("t", 0),))
        result = match_jobs([job], [tech])
        self.assertEqual(result.unmatched_job_ids, ("J",))

    def test_repeatable_and_weight_bounds(self):
        w = edge_weight_micro(distance_m=0, rating_milli=5_000, acceptance_milli=1_000)
        self.assertEqual(w, 1_000_000)
        far = edge_weight_micro(distance_m=50_000, rating_milli=0, acceptance_milli=0)
        self.assertGreaterEqual(far, 0)
        self.assertLess(far, 1_000)
        a = match_jobs(
            [Job("b", ("S",), (("t", 10),)), Job("a", ("S",), (("t", 10),))],
            [Technician("t", ("S",), 5_000, 1_000)],
        )
        b = match_jobs(
            [Job("a", ("S",), (("t", 10),)), Job("b", ("S",), (("t", 10),))],
            [Technician("t", ("S",), 5_000, 1_000)],
        )
        self.assertEqual(a, b)
        self.assertEqual(len(a.assignments), 1)

    def test_missing_distance_rejected(self):
        with self.assertRaises(MatchingError):
            match_jobs(
                [Job("J", ("S",), ())],
                [Technician("t", ("S",), 1_000, 1_000)],
            )


class PriorityTests(unittest.TestCase):
    def test_emergency_overrides_low_vulnerability_and_new_building(self):
        result = score_priority(HazardBand.EMERGENCY, 1, 0)
        self.assertEqual(result.priority_class, 1)
        self.assertTrue(result.emergency_override)
        # Without the override, S = 0.5*5 + 0.25*1 + 0.25*1 = 3, priority would be 3.
        self.assertEqual(result.rounded_score, 3)
        self.assertEqual(result.age_band, 1)

    def test_formula_edges(self):
        quiet = score_priority(HazardBand.INFORMATIONAL, 1, age_band_value=1)
        self.assertEqual(quiet.score_millis, 1000)
        self.assertEqual(quiet.priority_class, 5)
        severe = score_priority(HazardBand.HIGH, 5, age_band_value=5)
        # S = 0.5*4 + 0.25*5 + 0.25*5 = 2 + 1.25 + 1.25 = 4.5 -> 5, priority 1
        self.assertEqual(severe.rounded_score, 5)
        self.assertEqual(severe.priority_class, 1)

    def test_age_bands(self):
        self.assertEqual([age_band(y) for y in (0, 5, 6, 15, 16, 30, 31, 50, 51)], [1, 1, 2, 2, 3, 3, 4, 4, 5])

    def test_rejects(self):
        with self.assertRaises(PriorityError):
            score_priority(HazardBand.LOW, 0, 10)
        with self.assertRaises(PriorityError):
            score_priority(HazardBand.LOW, 3, -1)
        with self.assertRaises(PriorityError):
            age_band(True)  # type: ignore[arg-type]


class MeterTests(unittest.TestCase):
    def test_rollover_9999_to_0001(self):
        result = validate_meter_reading(1, [9999])
        self.assertEqual(result.status, MeterStatus.VALID)
        self.assertTrue(result.rollover)
        self.assertEqual(result.consumption, 2)

    def test_backwards_is_tamper(self):
        result = validate_meter_reading(4990, [5000])
        self.assertEqual(result.status, MeterStatus.TAMPERED_NEGATIVE)
        self.assertIsNone(result.consumption)

    def test_leak_against_flat_history(self):
        result = validate_meter_reading(200, [100, 110, 120])
        self.assertEqual(result.status, MeterStatus.SUSPECT_LEAK)
        self.assertEqual(result.consumption, 80)
        self.assertEqual(result.baseline, 10)

    def test_normal_increment(self):
        result = validate_meter_reading(130, [100, 110, 120])
        self.assertEqual(result.status, MeterStatus.VALID)
        self.assertEqual(result.consumption, 10)

    def test_zero_baseline_small_move_is_valid(self):
        result = validate_meter_reading(10, [0, 0, 0])
        self.assertEqual(result.status, MeterStatus.VALID)
        result = validate_meter_reading(50, [0, 0, 0])
        self.assertEqual(result.status, MeterStatus.SUSPECT_LEAK)

    def test_empty_history(self):
        result = validate_meter_reading(10, [])
        self.assertEqual(result.status, MeterStatus.VALID)
        self.assertIsNone(result.consumption)

    def test_bad_history_and_bounds(self):
        with self.assertRaises(MeterHistoryError):
            validate_meter_reading(10, [5000, 4990, 5000])
        with self.assertRaises(Exception):
            validate_meter_reading(-1, [0])
        with self.assertRaises(Exception):
            validate_meter_reading(10_000, [0])

    def test_repeatable(self):
        self.assertEqual(validate_meter_reading(1, [9999]), validate_meter_reading(1, [9999]))

    def test_exact_three_times_baseline_is_not_a_leak(self):
        exact = validate_meter_reading(150, [100, 110, 120])
        self.assertEqual(exact.consumption, 30)
        self.assertEqual(exact.baseline, 10)
        self.assertEqual(exact.status, MeterStatus.VALID)
        over = validate_meter_reading(151, [100, 110, 120])
        self.assertEqual(over.status, MeterStatus.SUSPECT_LEAK)
        self.assertEqual(over.consumption, 31)

    def test_rollover_quarter_dial_boundary(self):
        accepted = validate_meter_reading(0, [7500])
        self.assertEqual(accepted.status, MeterStatus.VALID)
        self.assertTrue(accepted.rollover)
        self.assertEqual(accepted.consumption, 2500)
        rejected = validate_meter_reading(1, [7500])
        self.assertEqual(rejected.status, MeterStatus.TAMPERED_NEGATIVE)
        just_below = validate_meter_reading(0, [7499])
        self.assertEqual(just_below.status, MeterStatus.TAMPERED_NEGATIVE)


class SecondPassTests(unittest.TestCase):
    def test_uuid_spellings_are_one_item(self):
        plain = _item(1, "RENT", date(2026, 1, 1), 50)
        braced = OpenItem(
            item_id="{00000000-0000-0000-0000-000000000001}",
            invoice_id=_id(9),
            tenant_id="t-1",
            charge_type="RENT",
            due_date=date(2026, 1, 1),
            balance_cents=50,
        )
        bare = OpenItem(
            item_id="00000000000000000000000000000001",
            invoice_id=_id(8),
            tenant_id="t-1",
            charge_type="WATER",
            due_date=date(2026, 1, 1),
            balance_cents=50,
        )
        with self.assertRaises(AllocationError):
            allocate_payment(payment_cents=100, tenant_id="t-1", currency="KES", items=[plain, braced])
        with self.assertRaises(AllocationError):
            allocate_payment(payment_cents=100, tenant_id="t-1", currency="KES", items=[plain, bare])

    def test_uuid_tie_break_is_bytes_not_text_order(self):
        # Mixed case: 'F' (0x46) < 'a' (0x61), so the raw strings sort 0x0F before 0x0A.
        # Byte order is the opposite. The smaller id, 0x0A, must be paid first.
        smaller = OpenItem(
            item_id="00000000-0000-0000-0000-00000000000a",
            invoice_id=_id(11),
            tenant_id="t-1",
            charge_type="WATER",
            due_date=date(2026, 1, 1),
            balance_cents=100,
        )
        larger = OpenItem(
            item_id="00000000-0000-0000-0000-00000000000F",
            invoice_id=_id(12),
            tenant_id="t-1",
            charge_type="WATER",
            due_date=date(2026, 1, 1),
            balance_cents=100,
        )
        self.assertLess(larger.item_id, smaller.item_id)
        self.assertLess(parse_uuid(smaller.item_id).bytes, parse_uuid(larger.item_id).bytes)
        result = allocate_payment(
            payment_cents=100, tenant_id="t-1", currency="KES", items=[larger, smaller]
        )
        self.assertEqual(result.lines[0].item_id, smaller.item_id)

    def test_urn_alias_is_one_item_and_infix_urn_is_rejected(self):
        plain = _item(1, "RENT", date(2026, 1, 1), 50)
        urn = OpenItem(
            item_id="urn:uuid:{00000000-0000-0000-0000-000000000001}",
            invoice_id=_id(7),
            tenant_id="t-1",
            charge_type="WATER",
            due_date=date(2026, 1, 1),
            balance_cents=50,
        )
        with self.assertRaises(AllocationError):
            allocate_payment(payment_cents=100, tenant_id="t-1", currency="KES", items=[plain, urn])
        with self.assertRaises(AllocationError):
            parse_uuid("00000000-0000-0000-0000-00000000urn:0001")
        with self.assertRaises(AllocationError):
            parse_uuid("{urn:uuid:00000000-0000-0000-0000-000000000001}")

    def test_period_start_before_uuid(self):
        later_period = OpenItem(
            item_id=_id(1),
            invoice_id=_id(21),
            tenant_id="t-1",
            charge_type="WATER",
            due_date=date(2026, 1, 10),
            period_start=date(2026, 1, 5),
            balance_cents=10,
        )
        earlier_period = OpenItem(
            item_id=_id(2),
            invoice_id=_id(22),
            tenant_id="t-1",
            charge_type="WATER",
            due_date=date(2026, 1, 10),
            period_start=date(2026, 1, 1),
            balance_cents=10,
        )
        result = allocate_payment(
            payment_cents=10, tenant_id="t-1", currency="KES", items=[later_period, earlier_period]
        )
        self.assertEqual(result.lines[0].item_id, earlier_period.item_id)

    def test_zero_balances_are_overpayment(self):
        result = allocate_payment(
            payment_cents=40,
            tenant_id="t-1",
            currency="KES",
            items=[_item(3, "RENT", date(2026, 1, 1), 0)],
        )
        self.assertEqual(result.state, AllocationState.OVERPAID)
        self.assertEqual(result.lines, ())
        self.assertEqual(result.overpayment_cents, 40)
        self.assertEqual(result.postings[1].account, "2020")

    def test_conservation_grid(self):
        items = [
            _item(1, "RENT", date(2026, 1, 1), 100),
            _item(2, "WATER", date(2026, 1, 2), 40),
            _item(3, "PENALTY", date(2026, 1, 1), 25),
            _item(4, "DEPOSIT", date(2026, 1, 1), 10),
            _item(5, "WATER", date(2026, 1, 2), 0),
        ]
        for pay in (0, 1, 39, 40, 65, 175, 176, 500):
            result = allocate_payment(payment_cents=pay, tenant_id="t-1", currency="KES", items=items)
            self.assertEqual(result.allocated_cents + result.overpayment_cents, pay)
            self.assertEqual(sum(line.amount_cents for line in result.lines), result.allocated_cents)
            debits = sum(p.amount_cents for p in result.postings if p.direction == "DEBIT")
            credits = sum(p.amount_cents for p in result.postings if p.direction == "CREDIT")
            self.assertEqual(debits, credits)
            self.assertNotIn("2030", {p.account for p in result.postings})
            classes = [line.priority_class for line in result.lines]
            self.assertEqual(classes, sorted(classes))

    def test_month_lengths_and_exact_half(self):
        cases = (
            (date(2026, 2, 1), 28),
            (date(2024, 2, 1), 29),
            (date(1900, 2, 1), 28),
            (date(2000, 2, 1), 29),
            (date(2026, 4, 1), 30),
            (date(2026, 7, 1), 31),
        )
        for move_in, days in cases:
            full = prorate_move_in(2_000_000, move_in)
            self.assertEqual(full.days_in_month, days)
            self.assertEqual(full.charge_cents, 2_000_000)
            last = prorate_move_in(1_000_000, date(move_in.year, move_in.month, days))
            self.assertEqual(last.occupied_days, 1)
            self.assertLessEqual(last.charge_cents, 1_000_000)
        # 15 cents * 1 / 30 is exactly 0.5 cent -> ROUND_HALF_UP to 1.
        half = prorate_move_in(15, date(2026, 9, 30))
        self.assertEqual(half.occupied_days, 1)
        self.assertEqual(half.charge_cents, 1)
        # Large intermediate product must stay exact (15/30 of 8e14).
        large = prorate_move_in(800_000_000_000_000, date(2026, 9, 16))
        self.assertEqual(large.charge_cents, 400_000_000_000_000)

    def test_hazard_rejects_bool_and_truncating_float(self):
        with self.assertRaises(PriorityError):
            score_priority(True, 1, 0)  # type: ignore[arg-type]
        with self.assertRaises(PriorityError):
            score_priority(5.9, 1, 0)  # type: ignore[arg-type]

    def test_half_score_rounds_up(self):
        # S = 0.50*1 + 0.25*1 + 0.25*3 = 1.5 -> priority 4. Not an emergency.
        result = score_priority(HazardBand.INFORMATIONAL, 1, 16)
        self.assertEqual(result.age_band, 3)
        self.assertEqual(result.score_millis, 1500)
        self.assertEqual(result.rounded_score, 2)
        self.assertEqual(result.priority_class, 4)
        self.assertFalse(result.emergency_override)

    def test_exp_half_micro_boundary(self):
        # Decimal exp(-15113/5000) = 48674.4999995… which is strictly below one-half.
        self.assertEqual(exp_decay_micro(15113), 48_674)
        self.assertEqual(exp_decay_micro(0), 1_000_000)
        self.assertEqual(exp_decay_micro(2000), 670_320)
        self.assertEqual(exp_decay_micro(5000), 367_879)

    def test_exp_distance_domain(self):
        # Last non-zero micro-unit at σ=5000 is d=72543 (series). d=72544 rounds to 0.
        # d >= 15*σ = 75000 returns 0 without the series. Same integer either way.
        self.assertEqual(exp_decay_micro(1), 999_800)
        self.assertEqual(exp_decay_micro(50_000), 45)
        self.assertEqual(exp_decay_micro(72_543), 1)
        self.assertEqual(exp_decay_micro(72_544), 0)
        self.assertEqual(exp_decay_micro(74_999), 0)
        self.assertEqual(exp_decay_micro(75_000), 0)
        self.assertEqual(exp_decay_micro(1_000_000), 0)
        self.assertEqual(exp_decay_micro(10**18), 0)
        self.assertEqual(exp_decay_micro(10**18, 5_000), 0)
        # Ratio 1 still uses the series, even when both magnitudes are large.
        self.assertEqual(exp_decay_micro(9_007_199_254_740_991, 9_007_199_254_740_991), 367_879)
        # σ=1: x=14 rounds to 1 micro; x=15 is the proven-zero cutoff.
        self.assertEqual(exp_decay_micro(14, 1), 1)
        self.assertEqual(exp_decay_micro(15, 1), 0)
        huge = edge_weight_micro(distance_m=10**18, rating_milli=5_000, acceptance_milli=1_000)
        self.assertEqual(huge, 500_000)
        self.assertEqual(edge_weight_micro(distance_m=10**18, rating_milli=0, acceptance_milli=0), 0)
        for bad in (-1, True, 1.5, float("inf"), float("nan")):
            with self.assertRaises(MatchingError):
                exp_decay_micro(bad)  # type: ignore[arg-type]
        for bad_sigma in (0, -1, True, 1.5, 5000.0, float("inf"), float("nan")):
            with self.assertRaises(MatchingError):
                exp_decay_micro(10, bad_sigma)  # type: ignore[arg-type]

    def test_rank_rejects_duplicate_technician_id(self):
        tech = Technician("t", ("S",), 1_000, 1_000)
        job = Job("J", ("S",), (("t", 0),))
        with self.assertRaises(MatchingError):
            rank_technicians(job, [tech, tech])

    def test_year_one_is_the_first_representable_date(self):
        # datetime.date starts at year 1. Year 1 is not a leap year.
        result = prorate_move_in(100, date(1, 2, 1))
        self.assertEqual(result.days_in_month, 28)
        self.assertEqual(result.occupied_days, 28)
        self.assertEqual(result.charge_cents, 100)

    def test_meter_config_rejects_non_ints(self):
        with self.assertRaises(MeterError):
            validate_meter_reading(1, [0], leak_factor_millis=3000.0)  # type: ignore[arg-type]
        with self.assertRaises(MeterError):
            validate_meter_reading(1, [0], leak_min_units=50.0)  # type: ignore[arg-type]
        with self.assertRaises(MeterError):
            validate_meter_reading(1, [0], leak_factor_millis=True)  # type: ignore[arg-type]
        with self.assertRaises(MeterError):
            validate_meter_reading(1, [0], leak_min_units=True)  # type: ignore[arg-type]

    def test_duplicate_distance_rejected(self):
        with self.assertRaises(MatchingError):
            match_jobs(
                [Job("J", ("S",), (("t", 1), ("t", 9)))],
                [Technician("t", ("S",), 1_000, 1_000)],
            )

    def test_equal_weight_tie_is_diagonal(self):
        techs = [Technician(f"t{i}", ("S",), 5_000, 1_000) for i in range(3)]
        jobs = [
            Job(f"j{i}", ("S",), tuple((f"t{j}", 0) for j in range(3)))
            for i in range(3)
        ]
        result = match_jobs(jobs, techs)
        self.assertEqual(
            [(a.job_id, a.technician_id) for a in result.assignments],
            [("j0", "t0"), ("j1", "t1"), ("j2", "t2")],
        )

    def test_weight_beats_a_cheaper_index(self):
        # Each job's nearest technician is the other's. Sum of indices favors the diagonal.
        jobs = [
            Job("j0", ("S",), (("t0", 5000), ("t1", 0))),
            Job("j1", ("S",), (("t0", 0), ("t1", 5000))),
        ]
        techs = [Technician(f"t{i}", ("S",), 5_000, 1_000) for i in range(2)]
        result = match_jobs(jobs, techs)
        self.assertEqual(
            [(a.job_id, a.technician_id) for a in result.assignments],
            [("j0", "t1"), ("j1", "t0")],
        )

    def test_weight_zero_edge_beats_unmatched(self):
        result = match_jobs(
            [Job("J", ("S",), (("t", 1_000_000),))],
            [Technician("t", ("S",), 0, 0)],
        )
        self.assertEqual(result.assignments[0].weight_micro, 0)
        self.assertEqual(result.unmatched_job_ids, ())

    def test_calendar_identity_for_century_years(self):
        for year in (1900, 2000, 2024, 2026):
            for month in range(1, 13):
                dim = calendar.monthrange(year, month)[1]
                full = prorate_move_in(1_234_567, date(year, month, 1))
                self.assertEqual(full.days_in_month, dim)
                self.assertEqual(full.charge_cents, 1_234_567)
                last = prorate_move_in(1_234_567, date(year, month, dim))
                self.assertEqual(last.occupied_days, 1)
                self.assertLessEqual(last.charge_cents, 1_234_567)

    def test_large_safe_integer_just_over_3x_is_a_leak(self):
        # Witness where float64(c*1000) == float64(b*3000) but c > 3b.
        # Readings stay inside the JS safe-integer range.
        baseline = 2_251_799_813_685_198
        consumption = 3 * baseline + 1
        captured = baseline + consumption
        result = validate_meter_reading(captured, [0, baseline], modulus=captured + 1)
        self.assertEqual(result.consumption, consumption)
        self.assertEqual(result.baseline, baseline)
        self.assertEqual(result.status, MeterStatus.SUSPECT_LEAK)
        exact = validate_meter_reading(baseline + 3 * baseline, [0, baseline], modulus=captured + 1)
        self.assertEqual(exact.status, MeterStatus.VALID)

    def test_rollover_above_baseline_names_the_reason(self):
        result = validate_meter_reading(0, [0, 10, 20, 7500])
        self.assertEqual(result.status, MeterStatus.SUSPECT_LEAK)
        self.assertTrue(result.rollover)
        self.assertEqual(result.consumption, 2500)
        self.assertEqual(result.baseline, 10)
        self.assertEqual(result.reason, "rollover consumption exceeds leak threshold")


def build_vectors() -> dict:
    prorations = []
    for cents, iso in (
        (2_000_000, "2026-09-01"),
        (1_000_000, "2026-07-31"),
        (1_000_000, "2026-09-16"),
        (1_234_567, "2026-01-17"),
        (1_234_567, "1900-02-01"),
        (1_234_567, "1900-02-28"),
        (1_234_567, "2000-02-01"),
        (1_234_567, "2000-02-29"),
    ):
        y, m, d = (int(x) for x in iso.split("-"))
        r = prorate_move_in(cents, date(y, m, d))
        prorations.append({
            "monthly_rent_cents": cents,
            "move_in": iso,
            "charge_cents": r.charge_cents,
            "occupied_days": r.occupied_days,
            "days_in_month": r.days_in_month,
        })
    water = _item(2, "WATER", date(2026, 2, 1), 1_000_000)
    rent = _item(1, "RENT", date(2026, 1, 1), 1_000_000)
    alloc = allocate_payment(payment_cents=1_000_000, tenant_id="t-1", currency="KES", items=[rent, water])
    over = allocate_payment(payment_cents=3_000_000, tenant_id="t-1", currency="KES", items=[_item(1, "RENT", date(2026, 1, 1), 2_500_000)])
    t1 = Technician("t1", ("PLUMBING", "ELECTRICAL"), 5_000, 1_000)
    t2 = Technician("t2", ("PLUMBING",), 5_000, 1_000)
    matched = match_jobs(
        [Job("A", ("PLUMBING",), (("t1", 0), ("t2", 2000))), Job("B", ("ELECTRICAL",), (("t1", 0), ("t2", 0)))],
        [t1, t2],
    )
    emergency = score_priority(HazardBand.EMERGENCY, 1, 0)
    quiet = score_priority(HazardBand.INFORMATIONAL, 1, age_band_value=1)
    roll = validate_meter_reading(1, [9999])
    leak = validate_meter_reading(200, [100, 110, 120])
    tamper = validate_meter_reading(4990, [5000])
    baseline = 2_251_799_813_685_198
    large_consumption = 3 * baseline + 1
    large_captured = baseline + large_consumption
    large_meter = validate_meter_reading(large_captured, [0, baseline], modulus=large_captured + 1)
    rollover_leak = validate_meter_reading(0, [0, 10, 20, 7500])
    crossed = match_jobs(
        [
            Job("j0", ("S",), (("t0", 5000), ("t1", 0))),
            Job("j1", ("S",), (("t0", 0), ("t1", 5000))),
        ],
        [Technician("t0", ("S",), 5_000, 1_000), Technician("t1", ("S",), 5_000, 1_000)],
    )
    half_score = score_priority(2, 1, 51)
    return {
        "proration": prorations,
        "allocation_water_before_rent": {
            "lines": [line.charge_type for line in alloc.lines],
            "state": alloc.state.value,
        },
        "overpayment": {
            "allocated_cents": over.allocated_cents,
            "overpayment_cents": over.overpayment_cents,
            "credit_account": "2020",
            "state": over.state.value,
        },
        "exp_decay_micro": {
            "0": exp_decay_micro(0),
            "5000": exp_decay_micro(5000),
            "2000": exp_decay_micro(2000),
            "15113": exp_decay_micro(15113),
            "1": exp_decay_micro(1),
            "50000": exp_decay_micro(50_000),
            "72543": exp_decay_micro(72_543),
            "72544": exp_decay_micro(72_544),
            "75000": exp_decay_micro(75_000),
            "1000000": exp_decay_micro(1_000_000),
            "sigma1_x14": exp_decay_micro(14, 1),
            "sigma1_x15": exp_decay_micro(15, 1),
        },
        "weight_perfect": edge_weight_micro(distance_m=0, rating_milli=5000, acceptance_milli=1000),
        "matching": {
            "pairs": {a.job_id: a.technician_id for a in matched.assignments},
            "weights": {a.job_id: a.weight_micro for a in matched.assignments},
        },
        "priority_emergency": {
            "priority_class": emergency.priority_class,
            "rounded_score": emergency.rounded_score,
            "score_millis": emergency.score_millis,
        },
        "priority_quiet": {"priority_class": quiet.priority_class, "score_millis": quiet.score_millis},
        "meter": {
            "rollover": {"status": roll.status.value, "consumption": roll.consumption, "rollover": roll.rollover},
            "leak": {"status": leak.status.value, "consumption": leak.consumption, "baseline": leak.baseline},
            "tamper": {"status": tamper.status.value, "consumption": tamper.consumption},
            "exact_3x": {
                "status": validate_meter_reading(150, [100, 110, 120]).status.value,
                "consumption": 30,
                "baseline": 10,
            },
            "just_over_3x": {
                "status": validate_meter_reading(151, [100, 110, 120]).status.value,
                "consumption": 31,
            },
            "rollover_cap": {
                "status": validate_meter_reading(0, [7500]).status.value,
                "consumption": 2500,
                "rollover": True,
            },
            "rollover_cap_plus_one": {
                "status": validate_meter_reading(1, [7500]).status.value,
                "consumption": None,
            },
            "rollover_leak": {
                "status": rollover_leak.status.value,
                "consumption": rollover_leak.consumption,
                "baseline": rollover_leak.baseline,
                "rollover": rollover_leak.rollover,
                "reason": rollover_leak.reason,
            },
            "large_just_over_3x": {
                "modulus": large_captured + 1,
                "captured": large_captured,
                "history": [0, baseline],
                "status": large_meter.status.value,
                "consumption": large_meter.consumption,
                "baseline": large_meter.baseline,
            },
            "zero_baseline_49": validate_meter_reading(49, [0, 0, 0]).status.value,
            "zero_baseline_50": validate_meter_reading(50, [0, 0, 0]).status.value,
        },
        "priority_half_up": {
            "score_millis": 1500,
            "rounded_score": 2,
            "priority_class": 4,
            "age_years": 16,
            "hazard": 1,
            "vulnerability": 1,
        },
        "priority_two_and_half": {
            "hazard": 2,
            "vulnerability": 1,
            "age_years": 51,
            "score_millis": half_score.score_millis,
            "rounded_score": half_score.rounded_score,
            "priority_class": half_score.priority_class,
        },
        "equal_weight_matching": [["j0", "t0"], ["j1", "t1"], ["j2", "t2"]],
        "crossed_matching": {
            "pairs": {a.job_id: a.technician_id for a in crossed.assignments},
            "weights": {a.job_id: a.weight_micro for a in crossed.assignments},
        },
        "proration_half_cent": {"monthly_rent_cents": 15, "move_in": "2026-09-30", "charge_cents": 1},
        "proration_large": {
            "monthly_rent_cents": 800_000_000_000_000,
            "move_in": "2026-09-16",
            "charge_cents": 400_000_000_000_000,
        },
    }


if __name__ == "__main__":
    unittest.main()
