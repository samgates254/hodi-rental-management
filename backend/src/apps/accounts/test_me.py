from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import AccountProfile
from apps.organizations.models import Organization, OrganizationMembership


class MeEndpointTests(APITestCase):
    def test_me_requires_authentication(self):
        response = self.client.get('/api/v1/accounts/me/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_profile_and_memberships(self):
        user = get_user_model().objects.create_user(
            username='manager',
            email='a@b.com',
            password='password',
            first_name='Ada',
            last_name='Owner',
        )
        organization = Organization.objects.create(name='Rongai Homes')
        AccountProfile.objects.create(
            user=user,
            account_type=AccountProfile.AccountType.OWNER,
            organization=organization,
            phone_number='+254700000001',
        )
        OrganizationMembership.objects.create(
            organization=organization,
            user=user,
            role=OrganizationMembership.Role.OWNER,
        )
        self.client.force_authenticate(user)

        response = self.client.get('/api/v1/accounts/me/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'manager')
        self.assertEqual(response.data['email'], 'a@b.com')
        self.assertEqual(response.data['account_type'], 'OWNER')
        self.assertEqual(response.data['organization_id'], organization.pk)
        self.assertEqual(response.data['phone_number'], '+254700000001')
        self.assertEqual(response.data['memberships'], [{
            'organization': organization.pk,
            'organization_name': 'Rongai Homes',
            'role': 'OWNER',
            'is_active': True,
        }])


class CorsOriginTests(APITestCase):
    def test_localhost_3000_and_5173_are_allowed(self):
        for origin in (
            'http://localhost:3000',
            'http://127.0.0.1:3000',
            'http://localhost:5173',
            'http://127.0.0.1:5173',
        ):
            response = self.client.options(
                '/api/v1/health/',
                HTTP_ORIGIN=origin,
                HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response['Access-Control-Allow-Origin'], origin)
