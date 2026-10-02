from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.leases.models import Lease
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant


class LeaseRoleAuthorizationTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='lease-user',
            password='password',
        )
        self.organization = Organization.objects.create(name='Rongai Homes')
        self.other_organization = Organization.objects.create(name='Other Homes')
        self.tenant = self.create_tenant(self.organization, 'Amina', 'Otieno')
        self.unit = self.create_unit(self.organization, 'Acacia Court', 'A-01')
        self.other_tenant = self.create_tenant(
            self.other_organization,
            'Brian',
            'Mwangi',
        )
        self.other_unit = self.create_unit(
            self.other_organization,
            'Other Court',
            'B-01',
        )
        self.lease = Lease.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            reference='LEASE-001',
            start_date=date(2026, 1, 1),
            monthly_rent_minor=2500000,
        )
        self.lease_url = reverse('leases:lease-detail', args=(self.lease.pk,))

    @staticmethod
    def create_tenant(organization, first_name, last_name):
        return Tenant.objects.create(
            organization=organization,
            first_name=first_name,
            last_name=last_name,
            phone_number='+254700000000',
        )

    @staticmethod
    def create_unit(organization, property_name, unit_name):
        property_record = Property.objects.create(
            organization=organization,
            name=property_name,
        )
        building = Building.objects.create(property=property_record, name='Block A')
        return Unit.objects.create(building=building, name=unit_name)

    def add_membership(self, organization, role):
        return OrganizationMembership.objects.create(
            organization=organization,
            user=self.user,
            role=role,
        )

    def test_accountant_can_read_but_not_write_leases(self):
        self.add_membership(
            self.organization,
            OrganizationMembership.Role.ACCOUNTANT,
        )
        self.client.force_authenticate(self.user)

        read_response = self.client.get(self.lease_url)
        update_response = self.client.patch(
            self.lease_url,
            {'monthly_rent_minor': 2700000},
            format='json',
        )
        create_response = self.client.post(
            reverse('leases:lease-list'),
            {
                'tenant': self.tenant.pk,
                'unit': self.unit.pk,
                'reference': 'LEASE-002',
                'start_date': date(2027, 1, 1).isoformat(),
                'monthly_rent_minor': 2500000,
            },
            format='json',
        )

        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_property_manager_cannot_move_lease_to_another_organization(self):
        self.add_membership(
            self.organization,
            OrganizationMembership.Role.PROPERTY_MANAGER,
        )
        self.add_membership(
            self.other_organization,
            OrganizationMembership.Role.ACCOUNTANT,
        )
        self.client.force_authenticate(self.user)

        response = self.client.patch(
            self.lease_url,
            {
                'tenant': self.other_tenant.pk,
                'unit': self.other_unit.pk,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.lease.refresh_from_db()
        self.assertEqual(self.lease.tenant, self.tenant)
        self.assertEqual(self.lease.unit, self.unit)