from datetime import date, datetime, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Organization, OrganizationMembership
from apps.leases.models import Lease
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant
from apps.utilities.models import UtilityAccount, UtilityBill


class UtilityApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username='utility-owner', password='password')
        self.accountant = user_model.objects.create_user(username='utility-accountant', password='password')
        self.technician = user_model.objects.create_user(username='utility-technician', password='password')
        self.organization = Organization.objects.create(name='Utility Homes')
        self.other_organization = Organization.objects.create(name='Other Homes')
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.owner, role=OrganizationMembership.Role.OWNER,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.accountant, role=OrganizationMembership.Role.ACCOUNTANT,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.technician, role=OrganizationMembership.Role.TECHNICIAN,
        )
        self.property = Property.objects.create(organization=self.organization, name='Riverside')
        self.building = Building.objects.create(property=self.property, name='Block A')
        self.unit = Unit.objects.create(building=self.building, name='A1')

    def test_owner_records_separately_scoped_utility_account_and_bill(self):
        self.client.force_authenticate(self.owner)
        account_response = self.client.post(
            reverse('utilities:utility-account-list'),
            {
                'organization': self.organization.pk,
                'property': self.property.pk,
                'unit': self.unit.pk,
                'service_type': 'ELECTRICITY',
                'provider_name': 'Kenya Power',
                'service_reference': 'ACCOUNT-001',
                'meter_reference': 'METER-001',
                'responsible_party': 'LANDLORD',
            },
            format='json',
        )
        self.assertEqual(account_response.status_code, 201)
        account = UtilityAccount.objects.get(pk=account_response.data['id'])
        self.assertEqual(account.created_by, self.owner)

        bill_response = self.client.post(
            reverse('utilities:utility-bill-list'),
            {
                'account': account.pk,
                'period_start': '2026-09-01',
                'period_end': '2026-09-30',
                'due_date': '2026-10-15',
                'amount_minor': 154200,
                'currency': 'KES',
                'reading_start': '100.000',
                'reading_end': '125.500',
                'reading_unit': 'kWh',
                'document_reference': 'LOCAL-REF-1',
            },
            format='json',
        )
        self.assertEqual(bill_response.status_code, 201)
        bill = UtilityBill.objects.get(pk=bill_response.data['id'])
        self.assertEqual(bill.amount_minor, 154200)
        self.assertEqual(bill.recorded_by, self.owner)

    def test_utility_bill_amount_above_storage_range_is_field_validation(self):
        account = UtilityAccount.objects.create(
            organization=self.organization,
            property=self.property,
            unit=self.unit,
            service_type='WATER',
            provider_name='Water provider',
            responsible_party=UtilityAccount.ResponsibleParty.LANDLORD,
            created_by=self.owner,
        )
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse('utilities:utility-bill-list'), {
            'account': account.pk,
            'period_start': '2026-09-01',
            'period_end': '2026-09-30',
            'amount_minor': 1 << 63,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('amount_minor', response.data)
        self.assertEqual(UtilityBill.objects.count(), 0)

    def test_accountant_can_read_but_not_write_utility_records(self):
        account = UtilityAccount.objects.create(
            organization=self.organization, property=self.property, service_type='WATER',
            provider_name='Nairobi Water', created_by=self.owner,
        )
        UtilityBill.objects.create(
            account=account, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            amount_minor=25000, recorded_by=self.owner,
        )
        self.client.force_authenticate(self.accountant)
        listed = self.client.get(reverse('utilities:utility-bill-list'))
        denied = self.client.post(
            reverse('utilities:utility-account-list'),
            {
                'organization': self.organization.pk, 'property': self.property.pk,
                'service_type': 'WATER', 'provider_name': 'Other provider', 'responsible_party': 'TENANT',
            },
            format='json',
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(denied.status_code, 403)

    def test_technician_cannot_read_utility_bills(self):
        self.client.force_authenticate(self.technician)
        response = self.client.get(reverse('utilities:utility-bill-list'))
        self.assertEqual(response.status_code, 403)

    def test_account_cannot_cross_property_organization_boundary(self):
        self.client.force_authenticate(self.owner)
        other_property = Property.objects.create(organization=self.other_organization, name='Other property')
        response = self.client.post(
            reverse('utilities:utility-account-list'),
            {
                'organization': self.organization.pk, 'property': other_property.pk,
                'service_type': 'WATER', 'provider_name': 'Water provider', 'responsible_party': 'LANDLORD',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(UtilityAccount.objects.count(), 0)

    def test_duplicate_bill_period_is_rejected_without_overwriting_record(self):
        account = UtilityAccount.objects.create(
            organization=self.organization, property=self.property, service_type='ELECTRICITY',
            provider_name='Kenya Power', created_by=self.owner,
        )
        UtilityBill.objects.create(
            account=account, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            amount_minor=10000, recorded_by=self.owner,
        )
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            reverse('utilities:utility-bill-list'),
            {'account': account.pk, 'period_start': '2026-09-01', 'period_end': '2026-09-30', 'amount_minor': 12000},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(UtilityBill.objects.get().amount_minor, 10000)

    def test_tenant_sees_only_tenant_responsibility_bills_for_current_leased_unit(self):
        user = get_user_model().objects.create_user(username='utility-tenant', password='password')
        tenant = Tenant.objects.create(organization=self.organization, user=user, first_name='T', last_name='One', phone_number='0700')
        Lease.objects.create(tenant=tenant, unit=self.unit, reference='UTILITY-TENANCY', start_date=date(2026, 1, 1), monthly_rent_minor=10000, status=Lease.Status.ACTIVE)
        tenant_account = UtilityAccount.objects.create(organization=self.organization, property=self.property, unit=self.unit,
            service_type='WATER', provider_name='Water provider', service_reference='PRIVATE', responsible_party='TENANT', created_by=self.owner)
        landlord_account = UtilityAccount.objects.create(organization=self.organization, property=self.property, unit=self.unit,
            service_type='ELECTRICITY', provider_name='Power provider', responsible_party='LANDLORD', created_by=self.owner)
        for account in (tenant_account, landlord_account):
            UtilityBill.objects.create(account=account, period_start=date(2026,9,1), period_end=date(2026,9,30),
                amount_minor=10000, document_reference='private-ref', recorded_by=self.owner)
        self.client.force_authenticate(user)
        response = self.client.get(reverse('utilities:tenant-utilities'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['utility_type'], 'Water')
        self.assertNotIn('PRIVATE', str(response.data))
        self.assertNotIn('provider_name', response.data[0])

    def test_deactivated_tenant_or_organization_cannot_read_tenant_utilities(self):
        user = get_user_model().objects.create_user(username='inactive-utility-tenant', password='password')
        tenant = Tenant.objects.create(
            organization=self.organization, user=user,
            first_name='Inactive', last_name='Tenant', phone_number='0700000099',
        )
        Lease.objects.create(
            tenant=tenant, unit=self.unit, reference='UTILITY-INACTIVE',
            start_date=date(2026, 1, 1), monthly_rent_minor=10000, status=Lease.Status.ACTIVE,
        )
        account = UtilityAccount.objects.create(
            organization=self.organization, property=self.property, unit=self.unit,
            service_type='WATER', provider_name='Water provider', responsible_party='TENANT',
            created_by=self.owner,
        )
        UtilityBill.objects.create(
            account=account, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            amount_minor=10000, recorded_by=self.owner,
        )
        self.client.force_authenticate(user)

        tenant.is_active = False
        tenant.save(update_fields=('is_active', 'updated_at'))
        inactive_tenant_response = self.client.get(reverse('utilities:tenant-utilities'))
        self.assertEqual(inactive_tenant_response.status_code, 200)
        self.assertEqual(inactive_tenant_response.data, [])

        tenant.is_active = True
        tenant.save(update_fields=('is_active', 'updated_at'))
        self.organization.is_active = False
        self.organization.save(update_fields=('is_active', 'updated_at'))
        inactive_organization_response = self.client.get(reverse('utilities:tenant-utilities'))
        self.assertEqual(inactive_organization_response.status_code, 200)
        self.assertEqual(inactive_organization_response.data, [])

    def test_consecutive_tenants_do_not_share_prior_period_utility_bill(self):
        previous_user = get_user_model().objects.create_user(username='previous-utility-tenant', password='password')
        current_user = get_user_model().objects.create_user(username='current-utility-tenant', password='password')
        previous_tenant = Tenant.objects.create(
            organization=self.organization, user=previous_user,
            first_name='Previous', last_name='Tenant', phone_number='0700000001',
        )
        current_tenant = Tenant.objects.create(
            organization=self.organization, user=current_user,
            first_name='Current', last_name='Tenant', phone_number='0700000002',
        )
        Lease.objects.create(
            tenant=previous_tenant, unit=self.unit, reference='UTILITY-PREVIOUS',
            start_date=date(2026, 1, 1), end_date=date(2026, 9, 13),
            monthly_rent_minor=10000, status=Lease.Status.EXPIRED,
        )
        Lease.objects.create(
            tenant=current_tenant, unit=self.unit, reference='UTILITY-CURRENT',
            start_date=date(2026, 9, 14), monthly_rent_minor=10000, status=Lease.Status.ACTIVE,
        )
        account = UtilityAccount.objects.create(
            organization=self.organization, property=self.property, unit=self.unit,
            service_type='WATER', provider_name='Water provider', responsible_party='TENANT',
            created_by=self.owner,
        )
        prior_bill = UtilityBill.objects.create(
            account=account, period_start=date(2026, 9, 1), period_end=date(2026, 9, 13),
            amount_minor=98765, recorded_by=self.owner,
        )
        current_bill = UtilityBill.objects.create(
            account=account, period_start=date(2026, 9, 14), period_end=date(2026, 9, 30),
            amount_minor=12345, recorded_by=self.owner,
        )

        self.client.force_authenticate(current_user)
        with patch('apps.utilities.views.rental_business_date', return_value=date(2026, 10, 14)):
            tenant_response = self.client.get(reverse('utilities:tenant-utilities'))
        self.assertEqual(tenant_response.status_code, 200)
        self.assertEqual([row['id'] for row in tenant_response.data], [current_bill.pk])
        self.assertNotIn(prior_bill.pk, [row['id'] for row in tenant_response.data])

        # Staff retain access to the historical account ledger.
        self.client.force_authenticate(self.owner)
        staff_response = self.client.get(reverse('utilities:utility-bill-list'))
        self.assertEqual(staff_response.status_code, 200)
        self.assertEqual({row['id'] for row in staff_response.data}, {prior_bill.pk, current_bill.pk})

        # Tenant role does not grant access to the staff utility collection.
        self.client.force_authenticate(current_user)
        self.assertEqual(self.client.get(reverse('utilities:utility-bill-list')).status_code, 403)

    def test_bill_beginning_on_first_day_of_current_lease_is_visible(self):
        user = get_user_model().objects.create_user(username='first-day-utility-tenant', password='password')
        tenant = Tenant.objects.create(
            organization=self.organization, user=user,
            first_name='First Day', last_name='Tenant', phone_number='0700000003',
        )
        Lease.objects.create(
            tenant=tenant, unit=self.unit, reference='UTILITY-FIRST-DAY',
            start_date=date(2026, 9, 14), monthly_rent_minor=10000, status=Lease.Status.ACTIVE,
        )
        account = UtilityAccount.objects.create(
            organization=self.organization, property=self.property, unit=self.unit,
            service_type='WATER', provider_name='Water provider', responsible_party='TENANT',
            created_by=self.owner,
        )
        bill = UtilityBill.objects.create(
            account=account, period_start=date(2026, 9, 14), period_end=date(2026, 9, 30),
            amount_minor=12345, recorded_by=self.owner,
        )

        self.client.force_authenticate(user)
        with patch('apps.utilities.views.rental_business_date', return_value=date(2026, 10, 14)):
            response = self.client.get(reverse('utilities:tenant-utilities'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data], [bill.pk])

    def test_bill_spanning_lease_transition_is_not_attributed_to_current_tenant(self):
        previous_user = get_user_model().objects.create_user(username='span-previous-tenant', password='password')
        current_user = get_user_model().objects.create_user(username='span-current-tenant', password='password')
        previous_tenant = Tenant.objects.create(
            organization=self.organization, user=previous_user,
            first_name='Previous', last_name='Tenant', phone_number='0700000004',
        )
        current_tenant = Tenant.objects.create(
            organization=self.organization, user=current_user,
            first_name='Current', last_name='Tenant', phone_number='0700000005',
        )
        Lease.objects.create(
            tenant=previous_tenant, unit=self.unit, reference='UTILITY-SPAN-PREVIOUS',
            start_date=date(2026, 1, 1), end_date=date(2026, 9, 13),
            monthly_rent_minor=10000, status=Lease.Status.EXPIRED,
        )
        Lease.objects.create(
            tenant=current_tenant, unit=self.unit, reference='UTILITY-SPAN-CURRENT',
            start_date=date(2026, 9, 14), monthly_rent_minor=10000, status=Lease.Status.ACTIVE,
        )
        account = UtilityAccount.objects.create(
            organization=self.organization, property=self.property, unit=self.unit,
            service_type='WATER', provider_name='Water provider', responsible_party='TENANT',
            created_by=self.owner,
        )
        spanning_bill = UtilityBill.objects.create(
            account=account, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            amount_minor=11111, recorded_by=self.owner,
        )

        self.client.force_authenticate(current_user)
        with patch('apps.utilities.views.rental_business_date', return_value=date(2026, 10, 14)):
            response = self.client.get(reverse('utilities:tenant-utilities'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

        self.client.force_authenticate(self.owner)
        staff_response = self.client.get(reverse('utilities:utility-bill-list'))
        self.assertEqual(staff_response.status_code, 200)
        self.assertEqual([row['id'] for row in staff_response.data], [spanning_bill.pk])

    def test_bill_stays_visible_through_nairobi_lease_end_day(self):
        user = get_user_model().objects.create_user(username='nairobi-date-tenant', password='password')
        tenant = Tenant.objects.create(
            organization=self.organization, user=user,
            first_name='Nairobi', last_name='Tenant', phone_number='0700000006',
        )
        Lease.objects.create(
            tenant=tenant, unit=self.unit, reference='UTILITY-NAIROBI-DATE',
            start_date=date(2026, 10, 15), end_date=date(2026, 10, 16),
            monthly_rent_minor=10000, status=Lease.Status.ACTIVE,
        )
        account = UtilityAccount.objects.create(
            organization=self.organization, property=self.property, unit=self.unit,
            service_type='WATER', provider_name='Water provider', responsible_party='TENANT',
            created_by=self.owner,
        )
        bill = UtilityBill.objects.create(
            account=account, period_start=date(2026, 10, 15), period_end=date(2026, 10, 16),
            amount_minor=12345, recorded_by=self.owner,
        )
        self.client.force_authenticate(user)

        before_utc_midnight = datetime(2026, 10, 14, 22, 30, tzinfo=datetime_timezone.utc)
        with patch('django.utils.timezone.now', return_value=before_utc_midnight):
            visible_on_start_day = self.client.get(reverse('utilities:tenant-utilities'))
        self.assertEqual(visible_on_start_day.status_code, 200)
        self.assertEqual([row['id'] for row in visible_on_start_day.data], [bill.pk])

        last_minute_of_nairobi_end_day = datetime(2026, 10, 16, 20, 59, tzinfo=datetime_timezone.utc)
        with patch('django.utils.timezone.now', return_value=last_minute_of_nairobi_end_day):
            visible_on_end_day = self.client.get(reverse('utilities:tenant-utilities'))
        self.assertEqual(visible_on_end_day.status_code, 200)
        self.assertEqual([row['id'] for row in visible_on_end_day.data], [bill.pk])

        after_nairobi_end_day = datetime(2026, 10, 16, 21, 30, tzinfo=datetime_timezone.utc)
        with patch('django.utils.timezone.now', return_value=after_nairobi_end_day):
            hidden_after_end_day = self.client.get(reverse('utilities:tenant-utilities'))
        self.assertEqual(hidden_after_end_day.status_code, 200)
        self.assertEqual(hidden_after_end_day.data, [])
