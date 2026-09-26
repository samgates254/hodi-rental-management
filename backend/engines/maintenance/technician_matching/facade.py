"""Matching boundary. Calls match_jobs. Does not rank jobs greedily."""

from __future__ import annotations

from rental_os.algorithms.matching import Job, MatchResult, MatchingError, Technician, match_jobs


def _job(value: Job) -> Job:
    if not isinstance(value, Job):
        raise MatchingError("job must be a canonical Job")
    if not isinstance(value.job_id, str) or value.job_id.strip() == "":
        raise MatchingError("job_id is required")
    return value


def _technician(value: Technician) -> Technician:
    if not isinstance(value, Technician):
        raise MatchingError("technician must be a canonical Technician")
    if not isinstance(value.technician_id, str) or value.technician_id.strip() == "":
        raise MatchingError("technician_id is required")
    if isinstance(value.rating_milli, bool) or not isinstance(value.rating_milli, int):
        raise MatchingError("rating_milli must be int")
    if isinstance(value.acceptance_milli, bool) or not isinstance(value.acceptance_milli, int):
        raise MatchingError("acceptance_milli must be int")
    return value


def match(*, jobs: list[Job] | tuple[Job, ...], technicians: list[Technician] | tuple[Technician, ...]) -> MatchResult:
    """Assign jobs with the canonical maximum-weight matching."""
    if not isinstance(jobs, (list, tuple)):
        raise MatchingError("jobs must be a list or tuple")
    if not isinstance(technicians, (list, tuple)):
        raise MatchingError("technicians must be a list or tuple")
    checked_jobs = tuple(_job(job) for job in jobs)
    checked_techs = tuple(_technician(tech) for tech in technicians)
    return match_jobs(checked_jobs, checked_techs)
