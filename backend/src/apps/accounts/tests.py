import re
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.apps import apps as model_apps
from django.core import mail
from django.core.cache import cache
from django.core import signing
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import AccountProfile
from apps.accounts.serializers import SignupSerializer
from apps.tenants.models import Tenant
from apps.marketplace.models import AgentProfile
from apps.accounts.services import make_email_verification_token

from apps.organizations.models import Organization, OrganizationMembership


class HealthCheckTests(TestCase):
    @patch('config.urls.connection.cursor')
    def test_health_endpoint_returns_ok(self, cursor_factory):
        cursor = cursor_factory.return_value.__enter__.return_value
        response = self.client.get('/api/v1/health/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})
        cursor.execute.assert_called_once_with('SELECT 1')
        cursor.fetchone.assert_called_once_with()

    @patch('config.urls.connection.cursor')
    def test_health_check_path_remains_compatible(self, cursor_factory):
        response = self.client.get(reverse('health-check'))

        self.assertEqual(reverse('health-check'), '/api/v1/health/')
        self.assertEqual(response.status_code, 200)
        cursor_factory.assert_called_once_with()

    @patch('config.urls.connection.cursor')
    def test_database_failure_returns_generic_503_without_exception_details(self, cursor_factory):
        cursor_factory.side_effect = RuntimeError(
            'postgres://user:secret@example.invalid/db SELECT sensitive_table'
        )

        response = self.client.get('/api/v1/health/')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'error', 'database': 'unavailable'})
        body = response.content.decode()
        for secret_part in ('secret', 'example.invalid', 'SELECT', 'sensitive_table'):
            self.assertNotIn(secret_part, body)


class AuthenticationApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='manager',
            password='password',
        )

    def test_authentication_endpoint_names_resolve_to_slash_terminated_routes(self):
        self.assertEqual(reverse('accounts:login'), '/api/v1/accounts/login/')
        self.assertEqual(reverse('accounts:google-login'), '/api/v1/accounts/google/')
        self.assertEqual(reverse('accounts:signup'), '/api/v1/accounts/signup/')
        self.assertEqual(reverse('accounts:logout'), '/api/v1/accounts/logout/')

        response = self.client.post(
            reverse('accounts:login'),
            {'username': 'manager', 'password': 'password'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['token'])

    def test_google_login_uses_existing_user_and_returns_their_single_account(self):
        self.user.email = 'manager@example.com'
        self.user.save(update_fields=('email',))
        with override_settings(GOOGLE_OAUTH_CLIENT_ID='google-client-id'), patch(
            'apps.accounts.views.verify_oauth2_token',
            return_value={'email': 'MANAGER@example.com', 'email_verified': True},
        ) as verify_token:
            response = self.client.post(
                reverse('accounts:google-login'),
                {'credential': 'verified-google-token'},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['token'])
        self.assertEqual(response.data['email'], 'manager@example.com')
        self.assertEqual(get_user_model().objects.count(), 1)
        verify_token.assert_called_once()
        self.assertEqual(verify_token.call_args.args[0], 'verified-google-token')
        self.assertEqual(verify_token.call_args.kwargs['audience'], 'google-client-id')

    @override_settings(GOOGLE_OAUTH_CLIENT_ID='google-client-id')
    @patch('apps.accounts.views.verify_oauth2_token')
    def test_google_login_rejects_unverified_or_unknown_emails_without_creating_users(self, verify_token):
        verify_token.return_value = {
            'email': 'manager@example.com',
            'email_verified': False,
        }
        unverified_response = self.client.post(
            reverse('accounts:google-login'),
            {'credential': 'unverified-token'},
            format='json',
        )
        verify_token.return_value = {
            'email': 'unknown@example.com',
            'email_verified': True,
        }
        unknown_response = self.client.post(
            reverse('accounts:google-login'),
            {'credential': 'unknown-email-token'},
            format='json',
        )

        self.assertEqual(unverified_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(unknown_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_user_can_have_only_one_account_profile(self):
        AccountProfile.objects.create(user=self.user)

        with self.assertRaises(IntegrityError), transaction.atomic():
            AccountProfile.objects.create(user=self.user)

    def test_frontend_auth_paths_match_django_routes_and_keep_trailing_slashes(self):
        repository_root = Path(__file__).resolve().parents[4]
        client_api = (repository_root / 'frontend/src/lib/clientApi.ts').read_text()
        configured_paths = dict(re.findall(
            r"^\s*(login|signup|logout): \"([^\"]+)\",$",
            client_api,
            re.MULTILINE,
        ))

        for frontend_name, django_name in (
            ('login', 'login'),
            ('signup', 'signup'),
            ('logout', 'logout'),
        ):
            with self.subTest(endpoint=frontend_name):
                frontend_path = configured_paths[frontend_name]
                self.assertTrue(frontend_path.endswith('/'))
                self.assertEqual(frontend_path, reverse(f'accounts:{django_name}'))

    def test_frontend_auth_requests_use_the_canonical_path_constants(self):
        repository_root = Path(__file__).resolve().parents[4]
        client_api = (repository_root / 'frontend/src/lib/clientApi.ts').read_text()

        for function_name, endpoint_name in (
            ('login', 'login'),
            ('register', 'signup'),
            ('logout', 'logout'),
        ):
            with self.subTest(function=function_name):
                function_start = client_api.index(f'export async function {function_name}(')
                following_function = client_api.find('\nexport ', function_start + 1)
                function_body = client_api[
                    function_start: following_function if following_function >= 0 else None
                ]
                self.assertIn(f'AUTH_API_PATHS.{endpoint_name}', function_body)

    def test_next_api_proxy_preserves_the_django_trailing_slash(self):
        repository_root = Path(__file__).resolve().parents[4]
        next_config = (repository_root / 'frontend/next.config.ts').read_text()

        self.assertIn('skipTrailingSlashRedirect: true', next_config)
        self.assertIn('source: "/api/v1/:path*"', next_config)
        self.assertIn('}/api/v1/:path*/', next_config)

    def test_login_returns_token_for_valid_credentials(self):
        self.user.first_name = 'Teresa'
        self.user.last_name = 'Njoroge'
        self.user.email = 'teresa@example.com'
        self.user.save(update_fields=('first_name', 'last_name', 'email'))
        response = self.client.post(
            '/api/v1/accounts/login/',
            {'username': 'manager', 'password': 'password'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['token'])
        self.assertEqual(response.data['first_name'], 'Teresa')
        self.assertEqual(response.data['last_name'], 'Njoroge')
        self.assertEqual(response.data['email'], 'teresa@example.com')
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
        self.assertEqual(
            response.data,
            {'non_field_errors': ['Unable to create an account with these details.']},
        )
        self.assertFalse(
            get_user_model().objects.filter(username='another-manager').exists(),
        )

    def test_signup_duplicate_identifier_errors_are_generic_and_consistent(self):
        self.user.email = 'manager@example.com'
        self.user.save(update_fields=('email',))
        initial_count = get_user_model().objects.count()
        duplicate_inputs = (
            ('manager', 'different@example.com', 'Username Duplicate Estate'),
            ('different-manager', 'manager@example.com', 'Email Duplicate Estate'),
            ('manager', 'manager@example.com', 'Both Duplicate Estate'),
        )
        responses = []

        for username, email, organization_name in duplicate_inputs:
            responses.append(self.client.post(
                reverse('accounts:signup'),
                {
                    'username': username,
                    'account_type': 'OWNER',
                    'organization_name': organization_name,
                    'email': email,
                    'password': 'A-strong-password-123!',
                    'password_confirm': 'A-strong-password-123!',
                },
                format='json',
            ))

        expected_error = {
            'non_field_errors': ['Unable to create an account with these details.'],
        }
        for response in responses:
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.data, expected_error)
            body = response.content.decode().lower()
            self.assertNotIn('manager', body)
            self.assertNotIn('example.com', body)

        self.assertEqual(get_user_model().objects.count(), initial_count)
        self.assertFalse(get_user_model().objects.filter(
            username__in=('different-manager',),
        ).exists())
        self.assertFalse(Organization.objects.filter(
            name__in=(name for _username, _email, name in duplicate_inputs),
        ).exists())

    def test_signup_rejects_case_insensitive_duplicate_email(self):
        self.user.email = 'Manager@Example.com'
        self.user.save(update_fields=('email',))

        response = self.client.post(
            reverse('accounts:signup'),
            {
                'username': 'another-manager',
                'account_type': 'OWNER',
                'organization_name': 'Case Duplicate Estate',
                'email': 'manager@example.COM',
                'password': 'A-strong-password-123!',
                'password_confirm': 'A-strong-password-123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {'non_field_errors': ['Unable to create an account with these details.']},
        )
        self.assertFalse(get_user_model().objects.filter(username='another-manager').exists())

    def test_database_email_index_allows_multiple_blank_emails(self):
        user_model = get_user_model()

        user_model.objects.create_user(
            username='blank-email-one', email='', password='password-one',
        )
        user_model.objects.create_user(
            username='blank-email-two', email='', password='password-two',
        )

        self.assertEqual(user_model.objects.filter(email='').count(), 3)

    def test_signup_database_email_race_returns_generic_error_and_rolls_back_owner(self):
        original_validate = SignupSerializer.validate

        def create_racing_signup(serializer, attrs):
            validated = original_validate(serializer, attrs)
            get_user_model().objects.create_user(
                username='race-winner',
                email=validated['email'],
                password='A-strong-password-123!',
            )
            return validated

        with patch.object(SignupSerializer, 'validate', create_racing_signup):
            response = self.client.post(
                reverse('accounts:signup'),
                {
                    'username': 'race-loser',
                    'account_type': 'OWNER',
                    'organization_name': 'Racing Estate',
                    'email': 'racing@example.com',
                    'password': 'A-strong-password-123!',
                    'password_confirm': 'A-strong-password-123!',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {'non_field_errors': ['Unable to create an account with these details.']},
        )
        self.assertTrue(get_user_model().objects.filter(username='race-winner').exists())
        self.assertFalse(get_user_model().objects.filter(username='race-loser').exists())
        self.assertFalse(Organization.objects.filter(name='Racing Estate').exists())

    def test_email_uniqueness_migration_detects_conflicts_without_exposing_addresses(self):
        from importlib import import_module

        migration = import_module(
            'apps.accounts.migrations.0003_user_email_ci_nonempty_unique',
        )
        user_model = get_user_model()
        index_name = connection.ops.quote_name(migration.INDEX_NAME)
        with connection.cursor() as cursor:
            cursor.execute(f'DROP INDEX {index_name}')
        try:
            user_model.objects.create_user(
                username='email-conflict-one',
                email='Conflict@Example.com',
                password='password-one',
            )
            user_model.objects.create_user(
                username='email-conflict-two',
                email='conflict@example.COM',
                password='password-two',
            )
            with self.assertRaises(RuntimeError) as raised:
                migration.check_existing_emails(model_apps, schema_editor=None)
        finally:
            user_model.objects.filter(
                username__in=('email-conflict-one', 'email-conflict-two'),
            ).delete()
            table = connection.ops.quote_name(user_model._meta.db_table)
            email_column = connection.ops.quote_name(user_model._meta.get_field('email').column)
            with connection.cursor() as cursor:
                cursor.execute(
                    f'CREATE UNIQUE INDEX {index_name} ON {table} (LOWER({email_column})) '
                    f"WHERE {email_column} <> ''"
                )

        self.assertIn('1 groups', str(raised.exception))
        self.assertNotIn('@', str(raised.exception))

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
        self.assertIn('#uid=', mail.outbox[0].body)
        self.assertIn('&token=', mail.outbox[0].body)
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
        reset_link = next(
            line.strip()
            for line in reset_email.splitlines()
            if '/password-reset/confirm#' in line
        )
        reset_values = parse_qs(urlsplit(reset_link).fragment)
        uid = reset_values['uid'][0]
        token = reset_values['token'][0]

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


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='accounts@example.com',
)
class AgentEmailVerificationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def signup_agent(self, *, username='verify-agent', email='verify-agent@example.com'):
        return self.client.post(
            reverse('accounts:signup'),
            {
                'username': username,
                'account_type': 'PROPERTY_AGENT',
                'email': email,
                'first_name': 'Nia',
                'last_name': 'Agent',
                'password': 'A-strong-password-123!',
                'password_confirm': 'A-strong-password-123!',
            },
            format='json',
        )

    def token_from_latest_email(self):
        message = mail.outbox[-1].body
        match = re.search(r'#token=([^\s]+)', message)
        self.assertIsNotNone(match)
        from urllib.parse import unquote

        return unquote(match.group(1))

    def test_agent_signup_requires_email_confirmation_before_login(self):
        response = self.signup_agent()
        user = get_user_model().objects.get(username='verify-agent')
        login = self.client.post(
            reverse('accounts:login'),
            {'username': 'verify-agent', 'password': 'A-strong-password-123!'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['email_verification_required'])
        self.assertIsNone(response.data['token'])
        self.assertFalse(Token.objects.filter(user=user).exists())
        self.assertEqual(login.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Token.objects.filter(user=user).exists())

    def test_valid_token_is_single_use_and_enables_agent_login(self):
        self.signup_agent()
        user = get_user_model().objects.get(username='verify-agent')
        token = self.token_from_latest_email()

        verified = self.client.post(
            reverse('accounts:email-verification-confirm'),
            {'token': token},
            format='json',
        )
        reused = self.client.post(
            reverse('accounts:email-verification-confirm'),
            {'token': token},
            format='json',
        )
        login = self.client.post(
            reverse('accounts:login'),
            {'username': 'verify-agent', 'password': 'A-strong-password-123!'},
            format='json',
        )

        self.assertEqual(verified.status_code, status.HTTP_200_OK)
        self.assertTrue(verified.data['token'])
        self.assertEqual(user.account_profile.email_verified_at is not None, True)
        self.assertEqual(user.agent_profile.verification_status, AgentProfile.VerificationStatus.UNVERIFIED)
        self.assertEqual(reused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_invalid_expired_and_email_changed_tokens_are_rejected(self):
        self.signup_agent()
        user = get_user_model().objects.get(username='verify-agent')
        invalid = self.client.post(
            reverse('accounts:email-verification-confirm'), {'token': 'not-a-token'}, format='json',
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

        with patch('django.core.signing.time.time', return_value=1_000):
            expired_token = make_email_verification_token(user)
        with override_settings(EMAIL_VERIFICATION_TOKEN_MAX_AGE=1):
            with patch('django.core.signing.time.time', return_value=1_002):
                expired = self.client.post(
                    reverse('accounts:email-verification-confirm'),
                    {'token': expired_token},
                    format='json',
                )
        self.assertEqual(expired.status_code, status.HTTP_400_BAD_REQUEST)

        changed_email_token = make_email_verification_token(user)
        user.email = 'changed@example.com'
        user.save(update_fields=('email',))
        changed_email = self.client.post(
            reverse('accounts:email-verification-confirm'),
            {'token': changed_email_token},
            format='json',
        )
        self.assertEqual(changed_email.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNone(user.account_profile.email_verified_at)

    def test_resend_has_generic_response_and_per_email_rate_limit(self):
        self.signup_agent()
        mail.outbox.clear()
        endpoint = reverse('accounts:email-verification-request')
        eligible = self.client.post(endpoint, {'email': 'verify-agent@example.com'}, format='json')
        unknown = self.client.post(endpoint, {'email': 'unknown@example.com'}, format='json')

        self.assertEqual(eligible.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(unknown.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(eligible.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)

        cache.clear()
        mail.outbox.clear()
        responses = [
            self.client.post(endpoint, {'email': 'verify-agent@example.com'}, format='json')
            for _ in range(4)
        ]
        self.assertTrue(all(response.status_code == status.HTTP_202_ACCEPTED for response in responses))
        self.assertEqual(len(mail.outbox), 3)
