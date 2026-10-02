from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from unittest.mock import patch
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import AccountProfile
from apps.tenants.models import Tenant

from apps.organizations.models import Organization, OrganizationMembership


class HealthCheckTests(TestCase):
    def test_health_endpoint_returns_ok(self):
        response = self.client.get('/api/v1/health/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})


class AuthenticationApiTests(TestCase):
    def setUp(self):
        cache.clear()
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

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='accounts@example.com',
    )
    def test_signup_activates_owner_immediately_without_sending_email(self):
        response = self.client.post(
            reverse('accounts:signup'),
            {
                'username': 'new-manager',
                'account_type': 'OWNER',
                'organization_name': 'New Estate',
                'email': 'new-manager@example.com',
                'first_name': 'New',
                'last_name': 'Manager',
                'phone_number': '+254700000001',
                'password': 'A-strong-password-123!',
                'password_confirm': 'A-strong-password-123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = get_user_model().objects.get(username='new-manager')
        self.assertTrue(user.check_password('A-strong-password-123!'))
        self.assertTrue(user.is_active)
        self.assertIsNone(user.account_profile.email_verified_at)
        self.assertEqual(user.account_profile.account_type, AccountProfile.AccountType.OWNER)
        self.assertEqual(user.account_profile.organization.name, 'New Estate')
        self.assertEqual(
            user.organization_memberships.get().role,
            'OWNER',
        )
        self.assertEqual(response.data['token'], Token.objects.get(user=user).key)
        self.assertEqual(response.data['account_type'], 'OWNER')
        self.assertEqual(response.data['organization_id'], user.account_profile.organization_id)
        self.assertEqual(mail.outbox, [])

    def test_tenant_can_skip_organization_and_select_it_later(self):
        response = self.client.post(
            reverse('accounts:signup'),
            {
                'username': 'new-tenant',
                'account_type': 'TENANT',
                'email': 'tenant@example.com',
                'first_name': 'Tia',
                'last_name': 'Tenant',
                'phone_number': '+254700000002',
                'password': 'A-strong-password-123!',
                'password_confirm': 'A-strong-password-123!',
            },
            format='json',
        )

        user = get_user_model().objects.get(username='new-tenant')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(user.is_active)
        self.assertIsNone(user.account_profile.organization_id)
        self.assertFalse(hasattr(user, 'tenant_record'))

        organization_response = self.client.get(reverse('accounts:organization-options'))
        self.assertEqual(organization_response.status_code, status.HTTP_200_OK)
        from apps.organizations.models import Organization

        organization = Organization.objects.create(name='Tenant Estate')
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
        assignment_response = self.client.post(
            reverse('accounts:tenant-organization'),
            {'organization_id': organization.pk},
            format='json',
        )

        self.assertEqual(assignment_response.status_code, status.HTTP_200_OK)
        self.assertEqual(Tenant.objects.get(user=user).organization, organization)

    def test_service_professional_signup_stores_selected_trade(self):
        response = self.client.post(
            reverse('accounts:signup'),
            {
                'username': 'electrician',
                'account_type': 'SERVICE_PROFESSIONAL',
                'professional_trade': 'ELECTRICIAN',
                'email': 'electrician@example.com',
                'password': 'A-strong-password-123!',
                'password_confirm': 'A-strong-password-123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        profile = get_user_model().objects.get(username='electrician').account_profile
        self.assertEqual(profile.account_type, AccountProfile.AccountType.SERVICE_PROFESSIONAL)
        self.assertEqual(profile.professional_trade, AccountProfile.ProfessionalTrade.ELECTRICIAN)

    def test_tenant_signup_does_not_require_email_verification_to_login_or_use_token(self):
        response = self.client.post(
            reverse('accounts:signup'),
            {
                'username': 'new-tenant',
                'account_type': 'TENANT',
                'email': 'tenant@example.com',
                'password': 'A-strong-password-123!',
                'password_confirm': 'A-strong-password-123!',
            },
            format='json',
        )
        login_response = self.client.post(
            reverse('accounts:login'),
            {'username': 'new-tenant', 'password': 'A-strong-password-123!'},
            format='json',
        )
        protected_response = self.client.get(
            '/api/v1/organizations/',
            HTTP_AUTHORIZATION=f"Token {response.data['token']}",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertEqual(protected_response.status_code, status.HTTP_200_OK)

    def test_signup_rejects_duplicate_email(self):
        self.user.email = 'manager@example.com'
        self.user.save(update_fields=('email',))

        response = self.client.post(
            reverse('accounts:signup'),
            {
                'username': 'another-manager',
                'account_type': 'OWNER',
                'organization_name': 'Another Estate',
                'email': 'manager@example.com',
                'password': 'A-strong-password-123!',
                'password_confirm': 'A-strong-password-123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            get_user_model().objects.filter(username='another-manager').exists(),
        )

    def test_signup_rejects_password_mismatch(self):
        response = self.client.post(
            reverse('accounts:signup'),
            {
                'username': 'new-manager',
                'account_type': 'OWNER',
                'organization_name': 'New Estate',
                'email': 'new-manager@example.com',
                'password': 'A-strong-password-123!',
                'password_confirm': 'a-different-password',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            get_user_model().objects.filter(username='new-manager').exists(),
        )

    def test_signup_rejects_password_that_fails_django_validation(self):
        response = self.client.post(
            reverse('accounts:signup'),
            {
                'username': 'new-manager',
                'account_type': 'OWNER',
                'organization_name': 'New Estate',
                'email': 'new-manager@example.com',
                'password': 'password',
                'password_confirm': 'password',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            get_user_model().objects.filter(username='new-manager').exists(),
        )

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='accounts@example.com',
    )
    def test_signup_is_rate_limited(self):
        payload = {
            'username': 'first-manager',
            'account_type': 'OWNER',
            'organization_name': 'First Estate',
            'email': 'first@example.com',
            'password': 'A-strong-password-123!',
            'password_confirm': 'A-strong-password-123!',
        }
        responses = []
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'auth_signup': '1/hour'}):
            for index in range(2):
                payload.update(
                    username=f'manager-{index}',
                    organization_name=f'Estate {index}',
                    email=f'manager-{index}@example.com',
                )
                responses.append(self.client.post(
                    reverse('accounts:signup'), payload, format='json',
                ))

        self.assertEqual(responses[0].status_code, status.HTTP_201_CREATED)
        self.assertEqual(responses[1].status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_login_is_rate_limited(self):
        self.user.is_active = True
        self.user.save(update_fields=('is_active',))
        profile = AccountProfile.objects.create(user=self.user)
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=('email_verified_at', 'updated_at'))
        responses = []
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'auth_login': '1/hour'}):
            for _ in range(2):
                responses.append(self.client.post(
                    reverse('accounts:login'),
                    {'username': 'manager', 'password': 'password'},
                    format='json',
                ))

        self.assertEqual(responses[0].status_code, status.HTTP_200_OK)
        self.assertEqual(responses[1].status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='accounts@example.com',
    )
    def test_password_reset_request_is_generic_and_emails_existing_account(self):
        self.user.email = 'manager@example.com'
        self.user.is_active = True
        self.user.save(update_fields=('email', 'is_active'))

        existing_response = self.client.post(
            reverse('accounts:password-reset-request'),
            {'email': 'manager@example.com'},
            format='json',
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('password-reset/confirm', mail.outbox[0].body)
        existing_payload = mail.outbox[0].body

        missing_response = self.client.post(
            reverse('accounts:password-reset-request'),
            {'email': 'missing@example.com'},
            format='json',
        )

        self.assertEqual(existing_response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(missing_response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(existing_response.data, missing_response.data)
        self.assertIn('uid=', existing_payload)
        self.assertIn('token=', existing_payload)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='accounts@example.com',
    )
    def test_password_reset_changes_password_and_revokes_existing_token(self):
        self.user.email = 'manager@example.com'
        self.user.is_active = True
        self.user.save(update_fields=('email', 'is_active'))
        old_token = Token.objects.create(user=self.user)
        self.client.post(
            reverse('accounts:password-reset-request'),
            {'email': self.user.email},
            format='json',
        )
        reset_email = mail.outbox[-1].body
        uid = reset_email.split('uid=', 1)[1].split()[0]
        token = reset_email.split('token=', 1)[1].split()[0]

        response = self.client.post(
            reverse('accounts:password-reset-confirm'),
            {
                'uid': uid,
                'token': token,
                'password': 'A-new-strong-password-456!',
                'password_confirm': 'A-new-strong-password-456!',
            },
            format='json',
        )

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.user.check_password('A-new-strong-password-456!'))
        self.assertFalse(Token.objects.filter(pk=old_token.pk).exists())
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.assertEqual(
            self.client.post(
                reverse('accounts:login'),
                {'username': 'manager', 'password': 'password'},
                format='json',
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.post(
                reverse('accounts:login'),
                {'username': 'manager', 'password': 'A-new-strong-password-456!'},
                format='json',
            ).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(
                reverse('accounts:password-reset-confirm'),
                {
                    'uid': uid,
                    'token': token,
                    'password': 'A-third-strong-password-789!',
                    'password_confirm': 'A-third-strong-password-789!',
                },
                format='json',
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_password_reset_rejects_mismatched_and_weak_passwords(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        self.user.email = 'manager@example.com'
        self.user.is_active = True
        self.user.save(update_fields=('email', 'is_active'))
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        mismatch_response = self.client.post(
            reverse('accounts:password-reset-confirm'),
            {
                'uid': uid,
                'token': token,
                'password': 'A-new-strong-password-456!',
                'password_confirm': 'A-different-password-123!',
            },
            format='json',
        )
        weak_response = self.client.post(
            reverse('accounts:password-reset-confirm'),
            {
                'uid': uid,
                'token': token,
                'password': 'password',
                'password_confirm': 'password',
            },
            format='json',
        )

        self.assertEqual(mismatch_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(weak_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(self.user.check_password('password'))

    @override_settings(PASSWORD_RESET_TIMEOUT=1)
    def test_password_reset_rejects_expired_token(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        self.user.email = 'manager@example.com'
        self.user.is_active = True
        self.user.save(update_fields=('email', 'is_active'))
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        with patch.object(default_token_generator, '_now') as mock_now:
            mock_now.return_value = timezone.datetime(2026, 1, 1)
            token = default_token_generator.make_token(self.user)
            mock_now.return_value = timezone.datetime(2026, 1, 1, 0, 0, 2)
            response = self.client.post(
                reverse('accounts:password-reset-confirm'),
                {
                    'uid': uid,
                    'token': token,
                    'password': 'A-new-strong-password-456!',
                    'password_confirm': 'A-new-strong-password-456!',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_request_is_rate_limited(self):
        responses = []
        with patch.dict(
            ScopedRateThrottle.THROTTLE_RATES,
            {'auth_password_reset_request': '1/hour'},
        ):
            for email in ('one@example.com', 'two@example.com'):
                responses.append(self.client.post(
                    reverse('accounts:password-reset-request'),
                    {'email': email},
                    format='json',
                ))

        self.assertEqual(responses[0].status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(responses[1].status_code, status.HTTP_429_TOO_MANY_REQUESTS)
