from datetime import date

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
