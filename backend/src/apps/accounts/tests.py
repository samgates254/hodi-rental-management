from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.organizations.models import Organization, OrganizationMembership


class HealthCheckTests(TestCase):
    def test_health_endpoint_returns_ok(self):
        response = self.client.get('/api/v1/health/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})


class AuthenticationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='manager',
            password='password',
        )

    def test_login_returns_token_for_valid_credentials(self):
        response = self.client.post(
            '/api/v1/accounts/login/',
            {'username': 'manager', 'password': 'password'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['token'])
        self.assertEqual(response.data['memberships'], [])

    def test_login_returns_active_organization_membership_details(self):
        organization = Organization.objects.create(name='Rongai Homes')
        OrganizationMembership.objects.create(
            organization=organization,
            user=self.user,
            role=OrganizationMembership.Role.CARETAKER,
        )
        inactive_organization = Organization.objects.create(
            name='Inactive Homes',
            is_active=False,
        )
        OrganizationMembership.objects.create(
            organization=inactive_organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
        )

        response = self.client.post(
            '/api/v1/accounts/login/',
            {'username': 'manager', 'password': 'password'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['memberships'],
            [{
                'organization_id': organization.pk,
                'organization_name': 'Rongai Homes',
                'role': OrganizationMembership.Role.CARETAKER,
            }],
        )

    def test_logout_revokes_current_token(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

        response = self.client.post('/api/v1/accounts/logout/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
