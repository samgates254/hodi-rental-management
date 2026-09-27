"""Tariff boundary. Prices validated consumption. Does not read meters."""

from __future__ import annotations

from datetime import date

from rental_os.algorithms.money import MoneyError, require_cents
from rental_os.algorithms.tariff import Tariff, TariffBand, TariffBill, TariffError, price_consumption


def _exact_date(value: object, name: str) -> date:
    if type(value) is not date:
        raise TariffError(f"{name} must be an exact datetime.date")
    return value


def _band(value: TariffBand) -> TariffBand:
    if not isinstance(value, TariffBand):
        raise TariffError("band must be a canonical TariffBand")
    if isinstance(value.price_cents_per_unit, bool) or not isinstance(value.price_cents_per_unit, int):
        raise MoneyError(
            f"price_cents_per_unit must be an int number of cents, got {type(value.price_cents_per_unit).__name__}"
        )
    require_cents(value.price_cents_per_unit, name="price_cents_per_unit")
    if value.up_to_units is not None and (
        isinstance(value.up_to_units, bool) or not isinstance(value.up_to_units, int)
    ):
        raise TariffError("up_to_units must be an int or unlimited")
    return value


def _tariff(value: Tariff) -> Tariff:
    if not isinstance(value, Tariff):
        raise TariffError("tariff must be a canonical Tariff")
    if not isinstance(value.tariff_id, str) or value.tariff_id.strip() == "":
        raise TariffError("tariff_id is required")
    if isinstance(value.fixed_charge_cents, bool) or not isinstance(value.fixed_charge_cents, int):
        raise MoneyError("fixed_charge_cents must be an int number of cents")
    if isinstance(value.minimum_charge_cents, bool) or not isinstance(value.minimum_charge_cents, int):
        raise MoneyError("minimum_charge_cents must be an int number of cents")
    require_cents(value.fixed_charge_cents, name="fixed_charge_cents")
    require_cents(value.minimum_charge_cents, name="minimum_charge_cents")
    if value.effective_from is not None:
        _exact_date(value.effective_from, "effective_from")
    if value.effective_to is not None:
        _exact_date(value.effective_to, "effective_to")
    if not isinstance(value.bands, tuple) or not value.bands:
        raise TariffError("bands are required")
    for band in value.bands:
        _band(band)
    return value


def price(*, consumption: int, tariffs: list[Tariff] | tuple[Tariff, ...], as_of: date) -> TariffBill:
    """Price one consumption figure. Meter state is not inspected."""
    as_of_date = _exact_date(as_of, "as_of")
    if isinstance(consumption, bool) or not isinstance(consumption, int):
        raise TariffError(f"consumption must be an int >= 0, got {type(consumption).__name__}")
    if not isinstance(tariffs, (list, tuple)) or not tariffs:
        raise TariffError("at least one tariff is required")
    checked = tuple(_tariff(tariff) for tariff in tariffs)
    return price_consumption(consumption=consumption, tariffs=checked, as_of=as_of_date)
