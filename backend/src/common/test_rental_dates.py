from datetime import date, datetime, timezone as datetime_timezone

from django.test import SimpleTestCase

from common.rental_dates import RENTAL_BUSINESS_TIME_ZONE, rental_business_date


class RentalBusinessDateTests(SimpleTestCase):
	def test_utc_yesterday_after_nairobi_midnight_is_today(self):
		instant = datetime(2026, 10, 14, 22, 30, tzinfo=datetime_timezone.utc)

		self.assertEqual(instant.astimezone(RENTAL_BUSINESS_TIME_ZONE).date(), date(2026, 10, 15))
		self.assertEqual(rental_business_date(instant), date(2026, 10, 15))

	def test_last_minute_of_nairobi_day_remains_that_business_date(self):
		instant = datetime(2026, 10, 14, 20, 59, tzinfo=datetime_timezone.utc)

		self.assertEqual(rental_business_date(instant), date(2026, 10, 14))

	def test_naive_timestamps_are_rejected(self):
		with self.assertRaises(ValueError):
			rental_business_date(datetime(2026, 10, 15, 1, 30))
