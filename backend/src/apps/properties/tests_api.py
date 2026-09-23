from datetime import date

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.leases.models import Lease
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant


class RentalApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='manager',
            password='password',
        )
        self.other_user = get_user_model().objects.create_user(
            username='other-manager',
            password='password',
        )
        self.organization = Organization.objects.create(
            name='Rongai Homes',
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.PROPERTY_MANAGER,
        )
        self.other_organization = Organization.objects.create(
            name='Other Homes',
        )
        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.other_user,
            role=OrganizationMembership.Role.PROPERTY_MANAGER,
        )

    def create_unit(self):
        property_record = Property.objects.create(
            organization=self.organization,
            name='Acacia Court',
        )
        building = Building.objects.create(
            property=property_record,
            name='Block A',
        )
        return Unit.objects.create(building=building, name='A-01')

    def create_tenant(self):
        return Tenant.objects.create(
            organization=self.organization,
            first_name='Amina',
            last_name='Otieno',
            phone_number='+254700000000',
        )

    def test_unauthenticated_user_cannot_access_properties(self):
        response = self.client.get(reverse('properties:property-list'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(CORS_ALLOWED_ORIGINS=['http://localhost:5173'])
    def test_allowed_frontend_origin_can_make_api_preflight_request(self):
        response = self.client.options(
            reverse('properties:property-list'),
            HTTP_ORIGIN='http://localhost:5173',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response['Access-Control-Allow-Origin'],
            'http://localhost:5173',
        )

    def test_authenticated_user_can_create_organization_and_becomes_owner(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(
            reverse('organizations:organization-list'),
            {'name': 'New Estate'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        organization = Organization.objects.get(name='New Estate')
        self.assertEqual(organization.slug, 'new-estate')
        self.assertTrue(
            OrganizationMembership.objects.filter(
                organization=organization,
                user=self.user,
                role=OrganizationMembership.Role.OWNER,
            ).exists(),
        )

    def test_user_can_create_property_in_own_organization(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(
            reverse('properties:property-list'),
            {'organization': self.organization.id, 'name': 'Acacia Court'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Acacia Court')

    def test_user_cannot_see_another_organization_property(self):
        Property.objects.create(
            organization=self.other_organization,
            name='Hidden Court',
        )
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse('properties:property-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_user_cannot_create_property_for_another_organization(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(
            reverse('properties:property-list'),
            {'organization': self.other_organization.id, 'name': 'Hidden Court'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_can_create_tenant_and_lease(self):
        unit = self.create_unit()
        tenant = self.create_tenant()
        self.client.force_authenticate(self.user)

        tenant_response = self.client.post(
            reverse('tenants:tenant-list'),
            {
                'organization': self.organization.id,
                'first_name': 'Brian',
                'last_name': 'Mwangi',
                'phone_number': '+254711111111',
            },
            format='json',
        )
        self.assertEqual(tenant_response.status_code, status.HTTP_201_CREATED)

        lease_response = self.client.post(
            reverse('leases:lease-list'),
            {
                'tenant': tenant.id,
                'unit': unit.id,
                'reference': 'LEASE-API-001',
                'start_date': date(2026, 1, 1).isoformat(),
                'monthly_rent_minor': 2500000,
                'security_deposit_minor': 2500000,
            },
            format='json',
        )

        self.assertEqual(lease_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Lease.objects.filter(reference='LEASE-API-001').exists())
