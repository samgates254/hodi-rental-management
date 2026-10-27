from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.organizations.models import Organization, OrganizationMembership
from apps.tenants.models import Tenant


class TenantAuthorizationTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username='owner', password='password')
        self.accountant = user_model.objects.create_user(username='accountant', password='password')
        self.support = user_model.objects.create_user(username='support', password='password')
        self.tenant_user = user_model.objects.create_user(username='tenant-user', password='password')
        self.organization = Organization.objects.create(name='Rongai Homes')
        self.other = Organization.objects.create(name='Other Homes')
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.owner, role=OrganizationMembership.Role.OWNER,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.accountant, role=OrganizationMembership.Role.ACCOUNTANT,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.support, role=OrganizationMembership.Role.SUPPORT,
        )
        self.tenant = Tenant.objects.create(
            organization=self.organization,
            user=self.tenant_user,
            first_name='Amina',
            last_name='Otieno',
            phone_number='+254700000010',
        )
        self.other_tenant = Tenant.objects.create(
            organization=self.other,
            first_name='Other',
            last_name='Person',
            phone_number='+254700000011',
        )

    def test_unauthenticated_tenant_list_is_rejected(self):
        response = self.client.get('/api/v1/tenants/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_accountant_can_read_but_not_write(self):
        self.client.force_authenticate(self.accountant)
        read_response = self.client.get('/api/v1/tenants/')
        write_response = self.client.post('/api/v1/tenants/', {
            'organization': self.organization.pk,
            'first_name': 'New',
            'last_name': 'Tenant',
            'phone_number': '+254700000099',
        }, format='json')
        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(read_response.data), 1)
        self.assertEqual(write_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_support_cannot_list_tenants(self):
        self.client.force_authenticate(self.support)
        response = self.client.get('/api/v1/tenants/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_tenant_sees_only_self_and_can_update_contact_fields(self):
        self.client.force_authenticate(self.tenant_user)
        listing = self.client.get('/api/v1/tenants/')
        other = self.client.get(f'/api/v1/tenants/{self.other_tenant.pk}/')
        update = self.client.patch(
            f'/api/v1/tenants/{self.tenant.pk}/',
            {'phone_number': '+254711111111', 'is_active': False},
            format='json',
        )
        contact = self.client.patch(
            f'/api/v1/tenants/{self.tenant.pk}/',
            {'phone_number': '+254711111111'},
            format='json',
        )
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in listing.data], [self.tenant.pk])
        self.assertEqual(other.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(update.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(contact.status_code, status.HTTP_200_OK)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.phone_number, '+254711111111')
        self.assertTrue(self.tenant.is_active)

    def test_owner_cannot_move_tenant_to_another_organization(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            f'/api/v1/tenants/{self.tenant.pk}/',
            {'organization': self.other.pk, 'first_name': 'Amina'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.organization_id, self.organization.pk)
        self.assertEqual(self.tenant.first_name, 'Amina')

    def test_inactive_tenant_cannot_use_self_service_after_deactivation(self):
        self.tenant.is_active = False
        self.tenant.save(update_fields=('is_active', 'updated_at'))
        self.client.force_authenticate(self.tenant_user)

        listing = self.client.get('/api/v1/tenants/')
        detail = self.client.get(f'/api/v1/tenants/{self.tenant.pk}/')
        update = self.client.patch(
            f'/api/v1/tenants/{self.tenant.pk}/',
            {'phone_number': '+254711111111'},
            format='json',
        )

        self.assertEqual(listing.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(detail.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(update.status_code, status.HTTP_403_FORBIDDEN)
