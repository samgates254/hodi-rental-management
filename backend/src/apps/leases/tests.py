from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.leases.models import Lease, LeaseAmendment, RentSchedule
from apps.leases.serializers import LeaseSerializer, RentScheduleSerializer
from django.contrib.auth import get_user_model
from apps.organizations.models import Organization
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant


class LeaseTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name='Rongai Homes',
            slug='rongai-homes',
        )
        property_record = Property.objects.create(
            organization=self.organization,
            name='Acacia Court',
        )
        building = Building.objects.create(
            property=property_record,
            name='Block A',
        )
        self.unit = Unit.objects.create(
            building=building,
            name='A-01',
        )
        self.tenant = Tenant.objects.create(
            organization=self.organization,
            first_name='Amina',
            last_name='Otieno',
            phone_number='+254700000000',
        )

    def test_overlapping_unit_leases_are_rejected(self):
        Lease.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            reference='LEASE-001',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            monthly_rent_minor=2500000,
        )
        overlapping = Lease(
            tenant=self.tenant,
            unit=self.unit,
            reference='LEASE-002',
            start_date=date(2026, 6, 1),
            end_date=date(2027, 5, 31),
            monthly_rent_minor=2500000,
        )

        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_inclusive_lease_end_rejects_same_day_successor_but_allows_next_day(self):
        previous = Lease.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            reference='LEASE-INCLUSIVE-PREVIOUS',
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 14),
            monthly_rent_minor=2500000,
        )
        next_tenant = Tenant.objects.create(
            organization=self.organization,
            first_name='Brian',
            last_name='Mwangi',
            phone_number='+254711111111',
        )
        same_day = Lease(
            tenant=next_tenant,
            unit=self.unit,
            reference='LEASE-INCLUSIVE-SAME-DAY',
            start_date=date(2026, 10, 14),
            end_date=date(2026, 12, 31),
            monthly_rent_minor=2500000,
        )
        next_day = Lease(
            tenant=next_tenant,
            unit=self.unit,
            reference='LEASE-INCLUSIVE-NEXT-DAY',
            start_date=date(2026, 10, 15),
            end_date=date(2026, 12, 31),
            monthly_rent_minor=2500000,
        )

        self.assertEqual(previous.end_date, date(2026, 10, 14))
        with self.assertRaises(ValidationError):
            same_day.full_clean()
        next_day.full_clean()

    def test_tenant_and_unit_must_share_an_organization(self):
        other_organization = Organization.objects.create(
            name='Other Homes',
            slug='other-homes',
        )
        other_tenant = Tenant.objects.create(
            organization=other_organization,
            first_name='Brian',
            last_name='Mwangi',
            phone_number='+254711111111',
        )
        lease = Lease(
            tenant=other_tenant,
            unit=self.unit,
            reference='LEASE-003',
            start_date=date(2026, 1, 1),
            monthly_rent_minor=2500000,
        )

        with self.assertRaises(ValidationError):
            lease.full_clean()

    def test_end_date_must_be_after_start_date(self):
        lease = Lease(
            tenant=self.tenant,
            unit=self.unit,
            reference='LEASE-004',
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 1),
            monthly_rent_minor=2500000,
        )

        with self.assertRaises(ValidationError):
            lease.full_clean()

    def test_lease_and_rent_schedule_amounts_reject_values_above_storage_range(self):
        maximum_plus_one = 1 << 63
        lease_serializer = LeaseSerializer(data={
            'tenant': self.tenant.pk,
            'unit': self.unit.pk,
            'reference': 'LEASE-OVERFLOW',
            'start_date': '2026-10-01',
            'monthly_rent_minor': maximum_plus_one,
        })
        self.assertFalse(lease_serializer.is_valid())
        self.assertIn('monthly_rent_minor', lease_serializer.errors)

        lease = Lease.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            reference='LEASE-SCHEDULE-OVERFLOW',
            start_date=date(2026, 1, 1),
            monthly_rent_minor=1000,
        )
        schedule_serializer = RentScheduleSerializer(data={
            'lease': lease.pk,
            'effective_from': '2026-01-01',
            'amount_minor': maximum_plus_one,
            'frequency': RentSchedule.Frequency.MONTHLY,
        })
        self.assertFalse(schedule_serializer.is_valid())
        self.assertIn('amount_minor', schedule_serializer.errors)

    def test_rent_schedule_rejects_overlapping_effective_dates(self):
        lease = Lease.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            reference='LEASE-005',
            start_date=date(2026, 1, 1),
            monthly_rent_minor=2500000,
        )
        RentSchedule.objects.create(
            lease=lease,
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 7, 1),
            amount_minor=2500000,
        )
        overlapping = RentSchedule(
            lease=lease,
            effective_from=date(2026, 6, 1),
            amount_minor=2700000,
        )

        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_lease_amendment_preserves_before_and_after_states(self):
        lease = Lease.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            reference='LEASE-006',
            start_date=date(2026, 1, 1),
            monthly_rent_minor=2500000,
        )
        user = get_user_model().objects.create_user(
            username='manager',
            password='password',
        )

        amendment = LeaseAmendment.objects.create(
            lease=lease,
            amendment_type=LeaseAmendment.AmendmentType.RENT_CHANGE,
            effective_date=date(2026, 7, 1),
            before_state={'monthly_rent_minor': 2500000},
            after_state={'monthly_rent_minor': 2700000},
            created_by=user,
        )

        self.assertEqual(amendment.before_state['monthly_rent_minor'], 2500000)
        self.assertEqual(amendment.after_state['monthly_rent_minor'], 2700000)
        self.assertEqual(amendment.created_by, user)
