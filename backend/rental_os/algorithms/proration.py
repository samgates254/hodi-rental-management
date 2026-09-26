"""Move-in rent proration in integer KES cents.

Blueprint §27 states P = round(R * ((D - d + 1) / D), 2). That expression is
implemented here in minor units with ROUND_HALF_UP so the result is deterministic
and never a binary float.

The full lease engine (segments, concessions, day-count conventions, gap
rejection) is the already-verified Phase 1A package at rental_os/phase_1a.
This function is the single-rate move-in case of that identity:

    occupied_days = D - d + 1
    charge_cents  = round_half_up(monthly_rent_cents * occupied_days / D)

Full-month identity: occupied_days == D implies charge == monthly rent.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from .money import require_cents, round_half_up_div


class ProrationError(ValueError):
    """Illegal proration input."""


@dataclass(frozen=True)
class MoveInProration:
    year: int
    month: int
    move_in_day: int
    days_in_month: int
    occupied_days: int
    monthly_rent_cents: int
    charge_cents: int

    @property
    def charge_kes(self) -> str:
        major, minor = divmod(self.charge_cents, 100)
        return f"{major}.{minor:02d}"


def prorate_move_in(monthly_rent_cents: int, move_in: date) -> MoveInProration:
    """Prorate one monthly rent for a move-in on `move_in` (inclusive).

    Preconditions
    - monthly_rent_cents is an int >= 0 (KES cents).
    - move_in is a real calendar date. The day is always valid for that month;
      a 31st cannot be constructed in a 30-day month, and Feb 29 only in leap years.

    Postconditions
    - 0 <= charge_cents <= monthly_rent_cents
    - occupied_days == days_in_month implies charge_cents == monthly_rent_cents
    - same inputs => same output

    Complexity: O(1)
    """
    rent = require_cents(monthly_rent_cents, name="monthly_rent_cents")
    if not isinstance(move_in, date):
        raise ProrationError("move_in must be a datetime.date")
    days_in_month = calendar.monthrange(move_in.year, move_in.month)[1]
    occupied = days_in_month - move_in.day + 1
    if occupied < 1 or occupied > days_in_month:
        raise ProrationError("occupied day count out of range")
    charge = round_half_up_div(rent * occupied, days_in_month)
    if charge > rent:
        raise ProrationError("proration exceeded monthly rent")
    return MoveInProration(
        year=move_in.year,
        month=move_in.month,
        move_in_day=move_in.day,
        days_in_month=days_in_month,
        occupied_days=occupied,
        monthly_rent_cents=rent,
        charge_cents=charge,
    )
