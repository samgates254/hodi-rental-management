"""Consumption to charge. Meter validation stays in meter.py.

Bands are cumulative thresholds in whole units, filled from the bottom.
The last band may be unlimited. Units above a capped schedule are rejected.

charge = max(fixed + band energy, minimum) when minimum > 0, else fixed + energy.
Zero consumption still pays the minimum when one is configured.
Prices are integer cents per unit. No float money.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .money import require_cents


class TariffError(ValueError):
    """Illegal tariff input."""


@dataclass(frozen=True)
class TariffBand:
    up_to_units: int | None
    price_cents_per_unit: int


@dataclass(frozen=True)
class Tariff:
    tariff_id: str
    bands: tuple[TariffBand, ...]
    fixed_charge_cents: int = 0
    minimum_charge_cents: int = 0
    effective_from: date | None = None
    effective_to: date | None = None


@dataclass(frozen=True)
class BandCharge:
    up_to_units: int | None
    units: int
    amount_cents: int


@dataclass(frozen=True)
class TariffBill:
    tariff_id: str
    consumption: int
    fixed_cents: int
    energy_cents: int
    minimum_cents: int
    charge_cents: int
    bands: tuple[BandCharge, ...]


def _units(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TariffError(f"{name} must be an int >= 0")
    return value


def _check_tariff(tariff: Tariff) -> None:
    if not tariff.tariff_id:
        raise TariffError("tariff_id is required")
    require_cents(tariff.fixed_charge_cents, name="fixed_charge_cents")
    require_cents(tariff.minimum_charge_cents, name="minimum_charge_cents")
    if tariff.effective_from is not None and not isinstance(tariff.effective_from, date):
        raise TariffError("effective_from must be a date")
    if tariff.effective_to is not None and not isinstance(tariff.effective_to, date):
        raise TariffError("effective_to must be a date")
    if (
        tariff.effective_from is not None
        and tariff.effective_to is not None
        and tariff.effective_to < tariff.effective_from
    ):
        raise TariffError("effective_to is before effective_from")
    previous = 0
    seen_open = False
    for band in tariff.bands:
        if seen_open:
            raise TariffError("unlimited band must be last")
        price = require_cents(band.price_cents_per_unit, name="price_cents_per_unit")
        del price
        if band.up_to_units is None:
            seen_open = True
            continue
        if isinstance(band.up_to_units, bool) or not isinstance(band.up_to_units, int):
            raise TariffError("up_to_units must be an int or unlimited")
        if band.up_to_units <= previous:
            raise TariffError("bands must be strictly increasing thresholds")
        previous = band.up_to_units


def _covers(tariff: Tariff, as_of: date) -> bool:
    if tariff.effective_from is not None and as_of < tariff.effective_from:
        return False
    if tariff.effective_to is not None and as_of > tariff.effective_to:
        return False
    return True


def price_consumption(
    *,
    consumption: int,
    tariffs: list[Tariff] | tuple[Tariff, ...],
    as_of: date,
) -> TariffBill:
    """Price one validated consumption against the unique effective tariff.

    Complexity: O(B) bands after a linear scan of the schedule.
    """
    units = _units(consumption, "consumption")
    if not isinstance(as_of, date):
        raise TariffError("as_of must be a date")
    if not tariffs:
        raise TariffError("at least one tariff is required")
    matches = []
    for tariff in tariffs:
        _check_tariff(tariff)
        if _covers(tariff, as_of):
            matches.append(tariff)
    if len(matches) != 1:
        raise TariffError(f"expected one effective tariff on {as_of.isoformat()}, found {len(matches)}")
    tariff = matches[0]
    remaining = units
    previous = 0
    energy = 0
    rows: list[BandCharge] = []
    for band in tariff.bands:
        if remaining == 0:
            break
        if band.up_to_units is None:
            take = remaining
        else:
            take = min(remaining, band.up_to_units - previous)
        amount = take * band.price_cents_per_unit
        rows.append(BandCharge(band.up_to_units, take, amount))
        energy += amount
        remaining -= take
        if band.up_to_units is not None:
            previous = band.up_to_units
    if remaining:
        raise TariffError("consumption exceeds the capped tariff")
    fixed = tariff.fixed_charge_cents
    subtotal = fixed + energy
    minimum = tariff.minimum_charge_cents
    charge = subtotal if minimum == 0 else max(subtotal, minimum)
    return TariffBill(
        tariff_id=tariff.tariff_id,
        consumption=units,
        fixed_cents=fixed,
        energy_cents=energy,
        minimum_cents=minimum,
        charge_cents=charge,
        bands=tuple(rows),
    )
