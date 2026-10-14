"""Civil-date helpers for rental business rules."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.utils import timezone


RENTAL_BUSINESS_TIME_ZONE = ZoneInfo('Africa/Nairobi')


def rental_business_date(at: datetime | None = None) -> date:
	"""Return the Nairobi civil date for an aware timestamp or current instant.

	Django continues to store and serialize aware timestamps according to its
	UTC default. DateField-based rental rules use the Kenyan civil calendar.
	"""
	moment = at if at is not None else timezone.now()
	if timezone.is_naive(moment):
		raise ValueError('rental_business_date requires a timezone-aware datetime.')
	return timezone.localdate(moment, timezone=RENTAL_BUSINESS_TIME_ZONE)
