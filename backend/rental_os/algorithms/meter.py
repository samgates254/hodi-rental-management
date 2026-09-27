"""Water-meter reading validator.

Status is one of VALID, SUSPECT_LEAK, TAMPERED_NEGATIVE.

Readings are dial integers in [0, modulus). Default modulus is 10_000
(4-digit dial). Consumption uses forward difference, with a rollover only
when the previous reading is in the top quarter of the dial and the wrapped
consumption is at most a quarter of the dial. Anything else that goes
backwards is TAMPERED_NEGATIVE (fail closed). 9999 -> 0001 is a rollover of 2.

Leak: current consumption > 3x the lower-median of historical consumptions.
If that median is 0, a jump of at least `leak_min_units` (default 50) is a leak.
Fewer than two historical readings means there is no consumption baseline, so
leak is not declared.

Historical decreases that are not plausible rollovers raise MeterHistoryError.
The function does not invent a baseline from a tampered series.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MeterError(ValueError):
    """Illegal meter input."""


class MeterHistoryError(MeterError):
    """Historical series contains a non-rollover decrease."""


class MeterStatus(str, Enum):
    VALID = "VALID"
    SUSPECT_LEAK = "SUSPECT_LEAK"
    TAMPERED_NEGATIVE = "TAMPERED_NEGATIVE"


@dataclass(frozen=True)
class MeterResult:
    status: MeterStatus
    consumption: int | None
    rollover: bool
    baseline: int | None
    reason: str


def _reading(value: int, modulus: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MeterError(f"{name} must be int")
    if value < 0 or value >= modulus:
        raise MeterError(f"{name} must be in 0..{modulus - 1}")
    return value


def step_consumption(previous: int, current: int, modulus: int) -> tuple[int, bool] | None:
    """Return (consumption, rollover) or None when the step is tamper."""
    if current >= previous:
        return (current - previous, False)
    wrapped = (modulus - previous) + current
    upper = (modulus * 3) // 4
    wrap_max = modulus // 4
    if previous >= upper and wrapped <= wrap_max:
        return (wrapped, True)
    return None


def _lower_median(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def validate_meter_reading(
    captured: int,
    history: list[int] | tuple[int, ...],
    *,
    modulus: int = 10_000,
    leak_factor_millis: int = 3_000,
    leak_min_units: int = 50,
) -> MeterResult:
    """Validate one captured dial reading against chronological history.

    Complexity: O(H log H) for the median. Deterministic. No I/O.
    """
    if isinstance(modulus, bool) or not isinstance(modulus, int) or modulus < 2:
        raise MeterError("modulus must be an int >= 2")
    if isinstance(leak_factor_millis, bool) or not isinstance(leak_factor_millis, int):
        raise MeterError("leak_factor_millis must be int")
    if isinstance(leak_min_units, bool) or not isinstance(leak_min_units, int):
        raise MeterError("leak_min_units must be int")
    if leak_factor_millis < 1_000:
        raise MeterError("leak_factor_millis must be >= 1000 (1x)")
    if leak_min_units < 0:
        raise MeterError("leak_min_units cannot be negative")
    current = _reading(captured, modulus, "captured")
    previous_readings = [_reading(v, modulus, "history") for v in history]
    if not previous_readings:
        return MeterResult(MeterStatus.VALID, None, False, None, "no baseline")

    historical_deltas: list[int] = []
    for left, right in zip(previous_readings, previous_readings[1:]):
        step = step_consumption(left, right, modulus)
        if step is None:
            raise MeterHistoryError("historical series contains a non-rollover decrease")
        historical_deltas.append(step[0])

    last = previous_readings[-1]
    step = step_consumption(last, current, modulus)
    if step is None:
        return MeterResult(
            MeterStatus.TAMPERED_NEGATIVE,
            None,
            False,
            _lower_median(historical_deltas) if historical_deltas else None,
            "negative dial movement is not a plausible rollover",
        )
    consumption, rollover = step
    if len(historical_deltas) < 1:
        reason = "rollover accepted" if rollover else "no consumption baseline"
        return MeterResult(MeterStatus.VALID, consumption, rollover, None, reason)

    baseline = _lower_median(historical_deltas)
    if baseline == 0:
        leak = consumption >= leak_min_units and leak_min_units > 0 or (
            leak_min_units == 0 and consumption > 0
        )
    else:
        leak = consumption * 1000 > baseline * leak_factor_millis
    if leak:
        why = "rollover consumption exceeds leak threshold" if rollover else "consumption exceeds leak threshold"
        return MeterResult(MeterStatus.SUSPECT_LEAK, consumption, rollover, baseline, why)
    why = "rollover within threshold" if rollover else "within baseline"
    return MeterResult(MeterStatus.VALID, consumption, rollover, baseline, why)
