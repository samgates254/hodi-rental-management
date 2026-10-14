"""Maximum-total-weight bipartite matching of work orders to technicians.

Blueprint weight, with scales made explicit so a 0–5 rating cannot swamp distance:

    W(j, t) = α · exp(-d(j, t) / σ) + β · (Rating(t) / 5) + γ · AcceptanceRate(t)

    α = 0.50, β = 0.30, γ = 0.20, σ = 5000 m

Skill category is a hard gate, not a weight. Unverified or unavailable
technicians, and technicians missing any required skill, have no edge.
Already-offered technicians (rejected or timed out) are excluded by the caller.

exp(-d/σ) is a fixed-point series so the integer weight does not depend on
libm. The assignment itself uses only integers. Jobs may remain unmatched.
The objective first maximizes total weight, then maximizes the number of
assignments among equal-score solutions, then minimizes the sum of edge
indices i·|T|+j after ids are sorted ascending. Thus a zero-score eligible
edge is used only when it does not reduce the total score; it wins a tie
against leaving that job unmatched. The index sum is not injective, so
several optima can share it; the Hungarian pivot returns one of them
deterministically. A single job still selects the lowest technician id.

Greedy "best score for this job" is not optimal when several jobs share a
pool. dispatch_candidates in maintenance_engine/dispatch.py is that greedy
ranker and also raises if any ineligible technician is passed in. Use
match_jobs instead. For a single job, rank_technicians is the same order
without raising on ineligible rows.
"""

from __future__ import annotations

from dataclasses import dataclass

ALPHA_MICRO = 500_000
BETA_MICRO = 300_000
GAMMA_MICRO = 200_000
SIGMA_M = 5_000
SERIES_SCALE = 10**15


class MatchingError(ValueError):
    """Illegal matching input."""


@dataclass(frozen=True)
class Job:
    job_id: str
    required_skills: tuple[str, ...]
    distance_m_by_technician: tuple[tuple[str, int], ...] = ()
    excluded_technician_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Technician:
    technician_id: str
    skills: tuple[str, ...]
    rating_milli: int
    acceptance_milli: int
    verified: bool = True
    available: bool = True


@dataclass(frozen=True)
class Assignment:
    job_id: str
    technician_id: str
    weight_micro: int


@dataclass(frozen=True)
class MatchResult:
    assignments: tuple[Assignment, ...]
    unmatched_job_ids: tuple[str, ...]


def div_trunc(numerator: int, denominator: int) -> int:
    """Toward-zero integer division. Mirrored in the TypeScript port."""
    if denominator <= 0:
        raise MatchingError("denominator must be positive")
    magnitude = abs(numerator) // denominator
    return -magnitude if numerator < 0 else magnitude


def exp_decay_micro(distance_m: int, sigma_m: int = SIGMA_M) -> int:
    """exp(-distance/sigma) in micro-units, ROUND_HALF_UP.

    Series at scale 10**15. Scale 10**12 mis-rounds d=15113
    (true value 48674.4999995…, which is below one-half) up to 48675.
    Each term uses toward-zero division.

    For every real x >= 15, exp(-x) * 1_000_000 < 1/2, because
    15 > ln(2_000_000) ≈ 14.508657738524219. ROUND_HALF_UP is then 0.
    Those ratios return 0 without the series. A truncated Taylor sum at
    large x grows like exp(+x) and is not a finite micro-unit.
    """
    if isinstance(distance_m, bool) or not isinstance(distance_m, int):
        raise MatchingError("distance_m must be int")
    if isinstance(sigma_m, bool) or not isinstance(sigma_m, int):
        raise MatchingError("sigma_m must be int")
    if distance_m < 0 or sigma_m <= 0:
        raise MatchingError("distance and sigma must be non-negative / positive")
    if distance_m == 0:
        return 1_000_000
    # Integer comparison: distance/sigma >= 15. Exact, no float.
    if distance_m >= 15 * sigma_m:
        return 0
    term = SERIES_SCALE
    total = term
    k = 0
    while True:
        k += 1
        term = div_trunc(term * (-distance_m), sigma_m * k)
        if term == 0:
            break
        total += term
        if k > 10_000:
            raise MatchingError("exp series did not converge")
    if total < 0:
        total = 0
    # Scale is 10**15; micro-units are 10**6, so divide by 10**9, half-up.
    return (total + 500_000_000) // 1_000_000_000


def edge_weight_micro(*, distance_m: int, rating_milli: int, acceptance_milli: int) -> int:
    """Integer micro-units of W. 1_000_000 micro = weight 1.0."""
    if not 0 <= rating_milli <= 5_000:
        raise MatchingError("rating_milli must be in 0..5000")
    if not 0 <= acceptance_milli <= 1_000:
        raise MatchingError("acceptance_milli must be in 0..1000")
    prox = exp_decay_micro(distance_m)
    rating_micro = (rating_milli * 1_000_000) // 5_000
    acc_micro = acceptance_milli * 1_000
    return (
        ALPHA_MICRO * prox + BETA_MICRO * rating_micro + GAMMA_MICRO * acc_micro
    ) // 1_000_000


def _hungarian_min(cost: list[list[int]]) -> list[int]:
    """Minimum-cost assignment. Returns column index per row. Square matrix."""
    n = len(cost)
    if n == 0:
        return []
    inf = 1 << 62
    u = [0] * (n + 1)
    v = [0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = inf
            j1 = 0
            for j in range(1, n + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assigned = [-1] * n
    for j in range(1, n + 1):
        if p[j] > 0:
            assigned[p[j] - 1] = j - 1
    return assigned


def _distance_map(pairs: tuple[tuple[str, int], ...]) -> dict[str, int]:
    out: dict[str, int] = {}
    for tech_id, distance in pairs:
        if tech_id in out:
            raise MatchingError(f"duplicate distance for technician {tech_id}")
        if isinstance(distance, bool) or not isinstance(distance, int) or distance < 0:
            raise MatchingError(f"distance for {tech_id} must be a non-negative int")
        out[tech_id] = distance
    return out


def _skills(values: tuple[str, ...]) -> frozenset[str]:
    return frozenset(s.strip().upper() for s in values if s and s.strip())


def match_jobs(jobs: list[Job] | tuple[Job, ...], technicians: list[Technician] | tuple[Technician, ...]) -> MatchResult:
    """Maximum-weight matching.

    Preconditions
    - ids unique and non-empty
    - distances are ints >= 0 for every technician the job might use
    - rating_milli in 0..5000, acceptance_milli in 0..1000

    Postconditions
    - each job and each technician appears at most once
    - every assignment is an eligible edge
    - total assignment weight is maximum
    - among equal scores, the assignment count is maximum
    - remaining ties use the documented index cost
    - repeated calls return the same assignments

    Complexity: O(n^3) with n = |J| + |T| after square padding.
    """
    if any(not j.job_id for j in jobs):
        raise MatchingError("job_id is required")
    if any(not t.technician_id for t in technicians):
        raise MatchingError("technician_id is required")
    if len({j.job_id for j in jobs}) != len(jobs):
        raise MatchingError("duplicate job_id")
    if len({t.technician_id for t in technicians}) != len(technicians):
        raise MatchingError("duplicate technician_id")

    job_rows = sorted(jobs, key=lambda j: j.job_id)
    tech_rows = sorted(technicians, key=lambda t: t.technician_id)
    n_j = len(job_rows)
    n_t = len(tech_rows)
    if n_j == 0:
        return MatchResult(assignments=(), unmatched_job_ids=())

    weight: list[list[int | None]] = [[None] * n_t for _ in range(n_j)]
    max_w = 0
    for i, job in enumerate(job_rows):
        required = _skills(job.required_skills)
        excluded = set(job.excluded_technician_ids)
        distances = _distance_map(job.distance_m_by_technician)
        for j, tech in enumerate(tech_rows):
            if tech.technician_id in excluded:
                continue
            if not tech.verified or not tech.available:
                continue
            have = _skills(tech.skills)
            if required and not required <= have:
                continue
            if tech.technician_id not in distances:
                raise MatchingError(
                    f"missing distance for job {job.job_id} technician {tech.technician_id}"
                )
            w = edge_weight_micro(
                distance_m=distances[tech.technician_id],
                rating_milli=tech.rating_milli,
                acceptance_milli=tech.acceptance_milli,
            )
            weight[i][j] = w
            if w > max_w:
                max_w = w

    # Pad with one dummy technician for each job and one dummy job for each
    # technician. This lets every real job remain unmatched even when there
    # are at least as many technicians as jobs. The former max(|J|, |T|)
    # padding had no dummy column in that case, which accidentally preferred
    # a scoreless real assignment over an unmatched job.
    n = n_j + n_t

    # Encode the documented lexicographic objective as one integer cost:
    # maximize score, then real assignment count, then minimize tie indices.
    # A total tie-cost difference is at most this bound.
    tie_limit = n_j * n_j * n_t
    assignment_unit = tie_limit + 1
    score_unit = n_j * assignment_unit + tie_limit + 1
    # Each unmatched job adds one assignment_unit, so an equal-score real
    # edge beats a dummy edge even after all tie costs are considered.
    dummy_cost = max_w * score_unit + assignment_unit
    # Forbidden edges must always lose to the available unmatched solution.
    forbidden = (max_w + 1) * score_unit

    cost = [[forbidden] * n for _ in range(n)]
    for i in range(n_j):
        for j in range(n_t):
            w = weight[i][j]
            if w is None:
                continue
            # Start at one so a zero-weight real edge is strictly worse than
            # its dummy alternative, whose tie cost is zero.
            tie = i * max(n_t, 1) + j + 1
            cost[i][j] = (max_w - w) * score_unit + tie
        for j in range(n_t, n):
            cost[i][j] = dummy_cost
    for i in range(n_j, n):
        for j in range(n):
            cost[i][j] = 0

    assigned = _hungarian_min(cost)
    pairs: list[Assignment] = []
    matched_jobs: set[str] = set()
    used_techs: set[str] = set()
    for i, j in enumerate(assigned):
        if i >= n_j or j < 0 or j >= n_t:
            continue
        w = weight[i][j]
        if w is None:
            continue
        tech_id = tech_rows[j].technician_id
        if tech_id in used_techs:
            raise MatchingError("technician assigned twice")
        used_techs.add(tech_id)
        job_id = job_rows[i].job_id
        matched_jobs.add(job_id)
        pairs.append(Assignment(job_id=job_id, technician_id=tech_id, weight_micro=w))
    pairs.sort(key=lambda a: a.job_id)
    unmatched = tuple(j.job_id for j in job_rows if j.job_id not in matched_jobs)
    return MatchResult(assignments=tuple(pairs), unmatched_job_ids=unmatched)


def rank_technicians(job: Job, technicians: list[Technician] | tuple[Technician, ...]) -> tuple[Assignment, ...]:
    """Single-job ranking. Ineligible technicians are skipped, not raised."""
    result = match_jobs([job], list(technicians))
    # Full order, not only the optimum: score every eligible edge.
    required = _skills(job.required_skills)
    excluded = set(job.excluded_technician_ids)
    distances = _distance_map(job.distance_m_by_technician)
    ranked: list[Assignment] = []
    for tech in technicians:
        if tech.technician_id in excluded or not tech.verified or not tech.available:
            continue
        if required and not required <= _skills(tech.skills):
            continue
        if tech.technician_id not in distances:
            raise MatchingError(f"missing distance for technician {tech.technician_id}")
        w = edge_weight_micro(
            distance_m=distances[tech.technician_id],
            rating_milli=tech.rating_milli,
            acceptance_milli=tech.acceptance_milli,
        )
        ranked.append(Assignment(job.job_id, tech.technician_id, w))
    ranked.sort(key=lambda a: (-a.weight_micro, a.technician_id))
    if result.assignments and ranked and result.assignments[0].technician_id != ranked[0].technician_id:
        raise MatchingError("single-job optimum disagrees with ranking")
    return tuple(ranked)
