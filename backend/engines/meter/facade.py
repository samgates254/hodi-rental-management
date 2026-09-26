"""Meter boundary. Validates dial state. Does not price consumption."""

from __future__ import annotations

from rental_os.algorithms.meter import MeterError, MeterResult, validate_meter_reading


def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MeterError(f"{name} must be int")
    return value


def validate(
    *,
    captured: int,
    history: list[int] | tuple[int, ...],
    modulus: int | None = None,
    leak_factor_millis: int | None = None,
    leak_min_units: int | None = None,
) -> MeterResult:
    """Validate one reading. Omitted dial parameters use the canonical signature."""
    current = _int(captured, "captured")
    if isinstance(history, (list, tuple)):
        readings = tuple(_int(value, "history") for value in history)
    else:
        raise MeterError("history must be a list or tuple")
    kwargs: dict[str, int] = {}
    if modulus is not None:
        kwargs["modulus"] = _int(modulus, "modulus")
    if leak_factor_millis is not None:
        kwargs["leak_factor_millis"] = _int(leak_factor_millis, "leak_factor_millis")
    if leak_min_units is not None:
        kwargs["leak_min_units"] = _int(leak_min_units, "leak_min_units")
    return validate_meter_reading(current, readings, **kwargs)
