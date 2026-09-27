"""Priority boundary. Direct delegation. No local score."""

from __future__ import annotations

from rental_os.algorithms.priority import HazardBand, PriorityError, PriorityResult, score_priority


def score(
    *,
    hazard: HazardBand | int,
    vulnerability: int,
    building_age_years: int | None,
    age_band_value: int | None,
) -> PriorityResult:
    """Score one report. Both age inputs are required arguments; pass None for the unused one."""
    if isinstance(hazard, bool) or isinstance(hazard, float):
        raise PriorityError("hazard must be an int band in 1..5, not a bool or float")
    if isinstance(vulnerability, bool) or not isinstance(vulnerability, int):
        raise PriorityError("vulnerability must be an int in 1..5")
    if building_age_years is not None and (
        isinstance(building_age_years, bool) or not isinstance(building_age_years, int)
    ):
        raise PriorityError("building_age_years must be int")
    if age_band_value is not None and (isinstance(age_band_value, bool) or not isinstance(age_band_value, int)):
        raise PriorityError("age_band must be an int in 1..5")
    return score_priority(
        hazard,
        vulnerability,
        building_age_years,
        age_band_value=age_band_value,
    )
