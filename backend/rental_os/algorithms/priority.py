"""Maintenance priority scorer.

Blueprint: S = 0.50*H + 0.25*V + 0.25*A, then a class in 1..5.
Emergency hazard overrides to priority 1 regardless of vulnerability or age.

H, V, and A are commensurate bands in 1..5. Raw building age in years is not
commensurate with a 1..5 hazard (a 40-year block would dominate), so age is
banded before it enters the formula.

Priority 1 is the most urgent class:
    rounded = ROUND_HALF_UP(S)
    priority = 1 if emergency else clamp(6 - rounded, 1, 5)

All arithmetic is integer millis. S_millis = 500*H + 250*V + 250*A.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class PriorityError(ValueError):
    """Illegal priority input."""


class HazardBand(IntEnum):
    INFORMATIONAL = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    EMERGENCY = 5


@dataclass(frozen=True)
class PriorityResult:
    hazard: HazardBand
    vulnerability: int
    age_band: int
    score_millis: int
    rounded_score: int
    priority_class: int
    emergency_override: bool


def age_band(building_age_years: int) -> int:
    """Map completed years to the 1..5 band the formula can actually use.

    0–5 -> 1, 6–15 -> 2, 16–30 -> 3, 31–50 -> 4, 51+ -> 5.
    """
    if isinstance(building_age_years, bool) or not isinstance(building_age_years, int):
        raise PriorityError("building_age_years must be int")
    if building_age_years < 0:
        raise PriorityError("building age cannot be negative")
    if building_age_years <= 5:
        return 1
    if building_age_years <= 15:
        return 2
    if building_age_years <= 30:
        return 3
    if building_age_years <= 50:
        return 4
    return 5


def _band(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise PriorityError(f"{name} must be an int in 1..5")
    return value


def score_priority(
    hazard: HazardBand | int,
    vulnerability: int,
    building_age_years: int | None = None,
    *,
    age_band_value: int | None = None,
) -> PriorityResult:
    """Score one report.

    Pass either building_age_years or age_band_value (1..5), not both absent.
    """
    if isinstance(hazard, bool) or isinstance(hazard, float):
        raise PriorityError("hazard must be an int band in 1..5, not a bool or float")
    try:
        if isinstance(hazard, HazardBand):
            hazard_band = hazard
        elif isinstance(hazard, int):
            hazard_band = HazardBand(hazard)
        else:
            raise PriorityError("hazard must be a HazardBand 1..5")
    except ValueError as exc:
        raise PriorityError("hazard must be a HazardBand 1..5") from exc
    v = _band(vulnerability, "vulnerability")
    if age_band_value is None:
        if building_age_years is None:
            raise PriorityError("building age or age band is required")
        a = age_band(building_age_years)
    else:
        if building_age_years is not None:
            raise PriorityError("pass age years or an age band, not both")
        a = _band(age_band_value, "age_band")
    score_millis = 500 * int(hazard_band) + 250 * v + 250 * a
    rounded = (score_millis + 500) // 1000
    if rounded < 1 or rounded > 5:
        raise PriorityError("rounded score escaped 1..5")
    emergency = hazard_band is HazardBand.EMERGENCY
    priority = 1 if emergency else (6 - rounded)
    return PriorityResult(
        hazard=hazard_band,
        vulnerability=v,
        age_band=a,
        score_millis=score_millis,
        rounded_score=rounded,
        priority_class=priority,
        emergency_override=emergency,
    )
