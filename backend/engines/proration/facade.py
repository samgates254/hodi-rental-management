"""Public move-in proration contract."""

from datetime import date

from rental_os.algorithms.proration import (
    MoveInProration,
    ProrationError,
    prorate_move_in as _prorate_move_in,
)


def prorate_move_in(monthly_rent_cents: int, move_in: date) -> MoveInProration:
    """Prorate monthly KES cents from an exact civil date, inclusively."""
    if type(move_in) is not date:
        raise ProrationError("move_in must be an exact datetime.date")
    return _prorate_move_in(monthly_rent_cents, move_in)


__all__ = ["MoveInProration", "ProrationError", "prorate_move_in"]
