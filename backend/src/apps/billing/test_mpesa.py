from datetime import date
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.billing.models import (
    Charge,
    DocumentStatus,
    Invoice,
    LedgerPosting,
    MpesaAttempt,
    Payment,
    PaymentAllocation,
)
from apps.organizations.models import Organization, OrganizationMembership
from apps.tenants.models import Tenant
from common.rental_dates import rental_business_date
from application.services.mpesa import initiate_mpesa_stk, kes_from_cents, normalize_kenya_msisdn
from infrastructure.payments.mpesa import MpesaClient, StkPushResult

CALLBACK_URL = 'https://example.test/api/v1/billing/mpesa/callback/test-token/'


class IdempotentTestAPIClient(APIClient):
    """Existing initiation fixtures use unique request keys by default."""

    def post(self, path, data=None, *args, **kwargs):
        if path.endswith('/mpesa/initiate/') and isinstance(data, dict):
            data = {**data}
            data.setdefault('idempotency_key', str(uuid.uuid4()))
        return super().post(path, data, *args, **kwargs)

MPESA_SETTINGS = dict(
    MPESA_BASE_URL='https://sandbox.safaricom.co.ke',
    MPESA_CONSUMER_KEY='test-key',
    MPESA_CONSUMER_SECRET='test-consumer-secret',
    MPESA_SHORTCODE='123456',
    MPESA_PASSKEY='test-passkey',
    MPESA_CALLBACK_URL=CALLBACK_URL,
    MPESA_CALLBACK_AUTH_TOKEN='test-token',
    MPESA_TIMEOUT_SECONDS=5,
    MPESA_TRANSACTION_TYPE='CustomerPayBillOnline',
)


def _accepted_result(**overrides):
    payload = dict(
        merchant_request_id='m-1',
        checkout_request_id='c-1',
        response_code='0',
        response_description='Success. Request accepted for processing',
        customer_message='Success. Request accepted for processing',
    )
    payload.update(overrides)
    return StkPushResult(**payload)


class FakeMpesaClient(MpesaClient):
    def __init__(self, result=None, error=None, **kwargs):
        super().__init__(
            base_url=MPESA_SETTINGS['MPESA_BASE_URL'],
            consumer_key=MPESA_SETTINGS['MPESA_CONSUMER_KEY'],
            consumer_secret=MPESA_SETTINGS['MPESA_CONSUMER_SECRET'],
            shortcode=MPESA_SETTINGS['MPESA_SHORTCODE'],
            passkey=MPESA_SETTINGS['MPESA_PASSKEY'],
            callback_url=MPESA_SETTINGS['MPESA_CALLBACK_URL'],
            callback_auth_token=MPESA_SETTINGS['MPESA_CALLBACK_AUTH_TOKEN'],
            urlopen=lambda request, timeout=None: None,
        )
        self.result = result if result is not None else _accepted_result()
        self.error = error
        self.stk_calls = []

    def stk_push(self, **kwargs):
        self.stk_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


@override_settings(**MPESA_SETTINGS)
class MpesaAttemptModelTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username='tenant-a', password='secret')
        self.organization = Organization.objects.create(name='Rongai Homes')
        self.tenant = Tenant.objects.create(
            organization=self.organization,
            user=self.user,
            first_name='Amina',
            last_name='Otieno',
            phone_number='+254700000010',
        )

    def _attempt(self, **overrides):
        payload = dict(
            organization=self.organization,
            tenant=self.tenant,
            initiated_by=self.user,
            amount_cents=150000,
            phone_number='254700000010',
        )
        payload.update(overrides)
        return MpesaAttempt.objects.create(**payload)

    def test_valid_attempt_creation(self):
        attempt = self._attempt()
        self.assertEqual(attempt.status, MpesaAttempt.Status.INITIATED)
        self.assertEqual(attempt.currency, 'KES')
        self.assertEqual(attempt.organization_id, self.organization.pk)
        self.assertEqual(attempt.tenant_id, self.tenant.pk)
        self.assertIsNone(attempt.merchant_request_id)
        self.assertIsNone(attempt.checkout_request_id)
        self.assertIsNone(attempt.mpesa_receipt_number)

    def test_organization_and_tenant_relationships(self):
        attempt = self._attempt()
        self.assertEqual(self.organization.mpesa_attempts.get(), attempt)
        self.assertEqual(self.tenant.mpesa_attempts.get(), attempt)

    def test_status_transitions_are_stored(self):
        attempt = self._attempt()
        for status_value in (
            MpesaAttempt.Status.STK_SENT,
            MpesaAttempt.Status.SUCCESS,
            MpesaAttempt.Status.FAILED,
            MpesaAttempt.Status.CANCELLED,
            MpesaAttempt.Status.TIMEOUT,
        ):
            attempt.status = status_value
            attempt.save(update_fields=('status', 'updated_at'))
            attempt.refresh_from_db()
            self.assertEqual(attempt.status, status_value)

    def test_null_provider_ids_are_allowed_together(self):
        first = self._attempt()
        second = self._attempt(amount_cents=20000)
        self.assertIsNone(first.checkout_request_id)
        self.assertIsNone(second.checkout_request_id)

    def test_checkout_request_id_is_unique_when_present(self):
        self._attempt(checkout_request_id='ws_CO_1')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._attempt(checkout_request_id='ws_CO_1', amount_cents=20000)

    def test_merchant_request_id_is_unique_when_present(self):
        self._attempt(merchant_request_id='m-dup')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._attempt(merchant_request_id='m-dup', amount_cents=20000)

    def test_receipt_number_is_unique_when_present(self):
        self._attempt(mpesa_receipt_number='NLJ7RT61SV')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._attempt(mpesa_receipt_number='NLJ7RT61SV', amount_cents=20000)


class MpesaPhoneAndAmountTests(TestCase):
    def test_phone_normalization(self):
        self.assertEqual(normalize_kenya_msisdn('+254700000010'), '254700000010')
        self.assertEqual(normalize_kenya_msisdn('0700000010'), '254700000010')
        self.assertEqual(normalize_kenya_msisdn('700000010'), '254700000010')
        self.assertEqual(normalize_kenya_msisdn('254711111111'), '254711111111')
        self.assertEqual(normalize_kenya_msisdn('0110000010'), '254110000010')

    def test_invalid_phone_rejected(self):
        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            normalize_kenya_msisdn('12345')
        with self.assertRaises(ValidationError):
            normalize_kenya_msisdn('+14155552671')
        with self.assertRaises(ValidationError):
            normalize_kenya_msisdn('')

    def test_amount_conversion_requires_whole_shillings(self):
        from rest_framework.exceptions import ValidationError

        self.assertEqual(kes_from_cents(150000), 1500)
        with self.assertRaises(ValidationError):
            kes_from_cents(0)
        with self.assertRaises(ValidationError):
            kes_from_cents(-100)
        with self.assertRaises(ValidationError):
            kes_from_cents(150)
        with self.assertRaises(ValidationError):
            kes_from_cents(True)


@override_settings(**MPESA_SETTINGS)
class MpesaInitiateApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.client = IdempotentTestAPIClient()
        self.tenant_user = user_model.objects.create_user(username='tenant', password='secret')
        self.other_user = user_model.objects.create_user(username='other-tenant', password='secret')
        self.owner = user_model.objects.create_user(username='owner', password='secret')
        self.organization = Organization.objects.create(name='Rongai Homes')
        self.other_org = Organization.objects.create(name='Other Homes')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
        )
        self.tenant = Tenant.objects.create(
            organization=self.organization,
            user=self.tenant_user,
            first_name='Amina',
            last_name='Otieno',
            phone_number='+254700000010',
        )
        self.other_tenant = Tenant.objects.create(
            organization=self.other_org,
            user=self.other_user,
            first_name='Other',
            last_name='Tenant',
            phone_number='+254700000099',
        )
        self.invoice = Invoice.objects.create(
            organization=self.organization,
            tenant=self.tenant,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            due_date=date(2026, 10, 5),
            status=DocumentStatus.POSTED,
            total_cents=150000,
            balance_cents=150000,
        )
        Charge.objects.create(
            invoice=self.invoice,
            organization=self.organization,
            tenant=self.tenant,
            charge_type='RENT',
            amount_cents=150000,
            balance_cents=150000,
            due_date=date(2026, 10, 5),
            lifecycle=DocumentStatus.POSTED,
        )
        self.other_invoice = Invoice.objects.create(
            organization=self.other_org,
            tenant=self.other_tenant,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            due_date=date(2026, 10, 5),
            status=DocumentStatus.POSTED,
            total_cents=50000,
            balance_cents=50000,
        )
        self.draft_invoice = Invoice.objects.create(
            organization=self.organization,
            tenant=self.tenant,
            period_start=date(2026, 11, 1),
            period_end=date(2026, 11, 30),
            due_date=date(2026, 11, 5),
            status=DocumentStatus.DRAFT,
            total_cents=10000,
            balance_cents=10000,
        )
        self.url = '/api/v1/billing/mpesa/initiate/'

    def _patch_client(self, fake):
        return patch('application.services.mpesa.MpesaClient.from_settings', return_value=fake)

    def test_unauthenticated_request_rejected(self):
        response = self.client.post(self.url, {'amount_cents': 10000}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(MpesaAttempt.objects.count(), 0)

    def test_owner_without_tenant_is_not_found(self):
        self.client.force_authenticate(self.owner)
        fake = FakeMpesaClient()
        with self._patch_client(fake):
            response = self.client.post(self.url, {'amount_cents': 10000}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(MpesaAttempt.objects.count(), 0)

    def test_initiate_creates_stk_sent_attempt_without_settlement(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        with self._patch_client(fake):
            response = self.client.post(self.url, {
                'amount_cents': 150000,
                'invoice': self.invoice.pk,
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['status'], MpesaAttempt.Status.STK_SENT)
        self.assertTrue(response.data['accepted'])
        self.assertFalse(response.data['payment_settled'])
        self.assertEqual(response.data['merchant_request_id'], 'm-1')
        self.assertEqual(response.data['checkout_request_id'], 'c-1')
        self.assertEqual(response.data['phone_number'], '254700000010')
        self.assertEqual(response.data['amount_cents'], 150000)
        attempt = MpesaAttempt.objects.get()
        self.assertEqual(attempt.status, MpesaAttempt.Status.STK_SENT)
        self.assertEqual(attempt.merchant_request_id, 'm-1')
        self.assertEqual(attempt.checkout_request_id, 'c-1')
        self.assertEqual(attempt.organization_id, self.organization.pk)
        self.assertEqual(attempt.tenant_id, self.tenant.pk)
        self.assertEqual(attempt.invoice_id, self.invoice.pk)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(PaymentAllocation.objects.count(), 0)
        self.assertEqual(LedgerPosting.objects.count(), 0)
        self.assertEqual(fake.stk_calls[0]['amount_kes'], 1500)
        self.assertEqual(fake.stk_calls[0]['phone_number'], '254700000010')

    def test_stk_accepted_does_not_mark_payment_successful(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        with self._patch_client(fake):
            response = self.client.post(self.url, {'amount_cents': 10000}, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertNotEqual(response.data['status'], MpesaAttempt.Status.SUCCESS)
        self.assertFalse(Payment.objects.filter(status=Payment.Status.ALLOCATED).exists())
        self.assertFalse(Payment.objects.filter(status=Payment.Status.PENDING).exists())

    def test_tenant_can_read_only_their_own_attempt_status(self):
        attempt = MpesaAttempt.objects.create(
            organization=self.organization, tenant=self.tenant, invoice=self.invoice,
            initiated_by=self.tenant_user, amount_cents=150000, phone_number='254700000010',
            status=MpesaAttempt.Status.STK_SENT, checkout_request_id='private-checkout',
        )
        self.client.force_authenticate(self.tenant_user)
        own = self.client.get(f'/api/v1/billing/mpesa/attempts/{attempt.pk}/')
        self.assertEqual(own.status_code, status.HTTP_200_OK)
        self.assertEqual(own.data['status'], 'PENDING')
        self.assertNotIn('phone_number', own.data)
        self.assertNotIn('checkout_request_id', own.data)
        self.client.force_authenticate(self.other_user)
        hidden = self.client.get(f'/api/v1/billing/mpesa/attempts/{attempt.pk}/')
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)

    def test_attempt_status_exposes_terminal_failure(self):
        attempt = MpesaAttempt.objects.create(
            organization=self.organization, tenant=self.tenant, invoice=self.invoice,
            initiated_by=self.tenant_user, amount_cents=150000, phone_number='254700000010',
            status=MpesaAttempt.Status.TIMEOUT,
        )
        self.client.force_authenticate(self.tenant_user)
        response = self.client.get(f'/api/v1/billing/mpesa/attempts/{attempt.pk}/')
        self.assertEqual(response.data['status'], 'EXPIRED')

    def test_nonzero_daraja_response_fails_without_settlement(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient(result=_accepted_result(
            response_code='1',
            merchant_request_id='m-fail',
            checkout_request_id='c-fail',
            response_description='Rejected',
        ))
        with self._patch_client(fake):
            response = self.client.post(self.url, {'amount_cents': 10000}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], MpesaAttempt.Status.FAILED)
        self.assertFalse(response.data['accepted'])
        self.assertFalse(response.data['payment_settled'])
        attempt = MpesaAttempt.objects.get()
        self.assertEqual(attempt.merchant_request_id, 'm-fail')
        self.assertEqual(attempt.checkout_request_id, 'c-fail')
        self.assertEqual(Payment.objects.count(), 0)

    def test_provider_timeout_stays_unresolved_and_retry_does_not_send_another_prompt(self):
        from infrastructure.payments.mpesa import MpesaTimeoutError

        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient(error=MpesaTimeoutError('Daraja request timed out.'))
        with self._patch_client(fake):
            response = self.client.post(self.url, {'amount_cents': 10000, 'idempotency_key': '8c35842b-d849-4fb0-9231-7ea815bd48c0'}, format='json')
            retried = self.client.post(self.url, {'amount_cents': 10000, 'idempotency_key': '8c35842b-d849-4fb0-9231-7ea815bd48c0'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(retried.data['id'], response.data['id'])
        attempt = MpesaAttempt.objects.get()
        self.assertEqual(attempt.status, MpesaAttempt.Status.INITIATED)
        self.assertEqual(attempt.reconciliation_state, MpesaAttempt.ReconciliationState.UNRESOLVED)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(len(fake.stk_calls), 1)

    def test_duplicate_payment_request_is_idempotent(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        payload = {'amount_cents': 10000, 'idempotency_key': '8c35842b-d849-4fb0-9231-7ea815bd48c0'}
        with self._patch_client(fake):
            first = self.client.post(self.url, payload, format='json')
            second = self.client.post(self.url, payload, format='json')
        self.assertEqual(first.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(second.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(second.data['id'], first.data['id'])
        self.assertEqual(MpesaAttempt.objects.count(), 1)
        self.assertEqual(len(fake.stk_calls), 1)

    def test_fresh_idempotency_keys_cannot_bypass_prompt_limit_and_retry_stays_idempotent(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        first_key = str(uuid.uuid4())
        first_attempt_id = None
        with self._patch_client(fake):
            for index in range(5):
                key = first_key if index == 0 else str(uuid.uuid4())
                response = self.client.post(self.url, {
                    'amount_cents': 10000,
                    'idempotency_key': key,
                    'phone_number': f'2547000001{index:02d}',
                }, format='json')
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
                if index == 0:
                    first_attempt_id = response.data['id']
                fake.result = _accepted_result(
                    merchant_request_id=f'm-{index + 2}',
                    checkout_request_id=f'c-{index + 2}',
                )

            limited = self.client.post(self.url, {
                'amount_cents': 10000,
                'idempotency_key': str(uuid.uuid4()),
            }, format='json')
            retried = self.client.post(self.url, {
                'amount_cents': 10000,
                'idempotency_key': first_key,
                'phone_number': '254700000100',
            }, format='json')

        self.assertEqual(limited.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(retried.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(retried.data['id'], first_attempt_id)
        self.assertEqual(MpesaAttempt.objects.filter(tenant=self.tenant).count(), 5)
        self.assertEqual(len(fake.stk_calls), 5)
        self.assertEqual(Payment.objects.count(), 0)

    def test_destination_prompt_limit_preserves_alternate_payer_phone_and_idempotency(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        first_key = str(uuid.uuid4())
        first_attempt_id = None
        with self._patch_client(fake):
            for index in range(3):
                key = first_key if index == 0 else str(uuid.uuid4())
                response = self.client.post(self.url, {
                    'amount_cents': 10000,
                    'idempotency_key': key,
                }, format='json')
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
                if index == 0:
                    first_attempt_id = response.data['id']
                fake.result = _accepted_result(
                    merchant_request_id=f'dest-m-{index + 2}',
                    checkout_request_id=f'dest-c-{index + 2}',
                )

            blocked = self.client.post(self.url, {
                'amount_cents': 10000,
                'idempotency_key': str(uuid.uuid4()),
            }, format='json')
            alternate = self.client.post(self.url, {
                'amount_cents': 10000,
                'idempotency_key': str(uuid.uuid4()),
                'phone_number': '254700000099',
            }, format='json')
            retried = self.client.post(self.url, {
                'amount_cents': 10000,
                'idempotency_key': first_key,
            }, format='json')

        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(alternate.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(retried.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(retried.data['id'], first_attempt_id)
        self.assertEqual(MpesaAttempt.objects.filter(tenant=self.tenant).count(), 4)
        self.assertEqual(len(fake.stk_calls), 4)
        self.assertEqual(Payment.objects.count(), 0)

    def test_idempotency_key_cannot_be_reused_for_different_payment(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        key = '8c35842b-d849-4fb0-9231-7ea815bd48c0'
        with self._patch_client(fake):
            first = self.client.post(self.url, {'amount_cents': 10000, 'idempotency_key': key}, format='json')
            conflict = self.client.post(self.url, {'amount_cents': 20000, 'idempotency_key': key}, format='json')
        self.assertEqual(first.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(conflict.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(MpesaAttempt.objects.count(), 1)
        self.assertEqual(len(fake.stk_calls), 1)

    def test_idempotency_key_is_required(self):
        unaided_client = APIClient()
        unaided_client.force_authenticate(self.tenant_user)
        response = unaided_client.post(self.url, {'amount_cents': 10000}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_amount_rejected(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        with self._patch_client(fake):
            zero = self.client.post(self.url, {'amount_cents': 0}, format='json')
            negative = self.client.post(self.url, {'amount_cents': -100}, format='json')
            fractional = self.client.post(self.url, {'amount_cents': 150}, format='json')
        self.assertEqual(zero.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(negative.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(fractional.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(MpesaAttempt.objects.count(), 0)
        self.assertEqual(fake.stk_calls, [])

    def test_amount_cannot_exceed_server_calculated_outstanding_balance(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        with self._patch_client(fake):
            response = self.client.post(self.url, {'amount_cents': 150100}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(MpesaAttempt.objects.count(), 0)
        self.assertEqual(fake.stk_calls, [])

    def test_partial_stk_payment_is_allowed_and_pending_attempt_reserves_balance(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        with self._patch_client(fake):
            first = self.client.post(self.url, {'amount_cents': 100000}, format='json')
            fake.result = _accepted_result(merchant_request_id='m-2', checkout_request_id='c-2')
            exceeds_unreserved = self.client.post(self.url, {'amount_cents': 60000}, format='json')
            remaining = self.client.post(self.url, {'amount_cents': 50000}, format='json')
        self.assertEqual(first.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(first.data['amount_cents'], 100000)
        self.assertEqual(exceeds_unreserved.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(remaining.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(MpesaAttempt.objects.count(), 2)
        self.assertEqual(len(fake.stk_calls), 2)

    def test_invalid_phone_rejected(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        with self._patch_client(fake):
            response = self.client.post(self.url, {
                'amount_cents': 10000,
                'phone_number': '12345',
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(MpesaAttempt.objects.count(), 0)

    @override_settings(MPESA_CONSUMER_KEY='')
    def test_missing_provider_configuration_fails_closed_without_creating_attempt(self):
        self.client.force_authenticate(self.tenant_user)
        response = self.client.post(self.url, {'amount_cents': 10000}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'M-Pesa is not configured.')
        self.assertEqual(MpesaAttempt.objects.count(), 0)

    def test_tenant_cannot_pay_another_organizations_invoice(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        with self._patch_client(fake):
            response = self.client.post(self.url, {
                'amount_cents': 10000,
                'invoice': self.other_invoice.pk,
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(MpesaAttempt.objects.count(), 0)

    def test_tenant_cannot_initiate_for_another_tenant(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        with self._patch_client(fake):
            response = self.client.post(self.url, {
                'amount_cents': 10000,
                'tenant': self.other_tenant.pk,
                'organization': self.other_org.pk,
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        attempt = MpesaAttempt.objects.get()
        self.assertEqual(attempt.tenant_id, self.tenant.pk)
        self.assertEqual(attempt.organization_id, self.organization.pk)
        self.assertNotEqual(attempt.tenant_id, self.other_tenant.pk)

    def test_other_tenant_cannot_use_this_invoice(self):
        self.client.force_authenticate(self.other_user)
        fake = FakeMpesaClient()
        with self._patch_client(fake):
            response = self.client.post(self.url, {
                'amount_cents': 10000,
                'invoice': self.invoice.pk,
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(MpesaAttempt.objects.count(), 0)

    def test_draft_invoice_rejected(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        with self._patch_client(fake):
            response = self.client.post(self.url, {
                'amount_cents': 10000,
                'invoice': self.draft_invoice.pk,
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(MpesaAttempt.objects.count(), 0)

    def test_phone_override_is_normalized(self):
        self.client.force_authenticate(self.tenant_user)
        fake = FakeMpesaClient()
        with self._patch_client(fake):
            response = self.client.post(self.url, {
                'amount_cents': 10000,
                'phone_number': '0711111111',
            }, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['phone_number'], '254711111111')
        self.assertEqual(fake.stk_calls[0]['phone_number'], '254711111111')

    def test_service_does_not_create_ledger_rows(self):
        fake = FakeMpesaClient()
        attempt = initiate_mpesa_stk(
            actor=self.tenant_user,
            amount_cents=20000,
            client=fake,
        )
        self.assertEqual(attempt.status, MpesaAttempt.Status.STK_SENT)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(PaymentAllocation.objects.count(), 0)
        self.assertEqual(LedgerPosting.objects.count(), 0)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_cents, 150000)
        self.assertEqual(self.invoice.status, DocumentStatus.POSTED)


@skipUnless(connection.vendor == 'postgresql', 'Requires PostgreSQL row-level locking semantics.')
@override_settings(**MPESA_SETTINGS)
class MpesaInitiationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user_model = get_user_model()
        self.tenant_user = user_model.objects.create_user(username='concurrent-stk-tenant', password='secret')
        self.organization = Organization.objects.create(name='Concurrent STK Homes')
        self.tenant = Tenant.objects.create(
            organization=self.organization,
            user=self.tenant_user,
            first_name='Amina',
            last_name='Otieno',
            phone_number='+254700000010',
        )
        today = rental_business_date()
        invoice = Invoice.objects.create(
            organization=self.organization,
            tenant=self.tenant,
            period_start=today.replace(day=1),
            period_end=today,
            due_date=today,
            status=DocumentStatus.POSTED,
            total_cents=150000,
            balance_cents=150000,
        )
        Charge.objects.create(
            invoice=invoice,
            organization=self.organization,
            tenant=self.tenant,
            charge_type='RENT',
            amount_cents=150000,
            balance_cents=150000,
            due_date=today,
            lifecycle=DocumentStatus.POSTED,
        )

    def test_concurrent_prompts_cannot_reserve_more_than_open_rent_balance(self):
        fake = FakeMpesaClient()
        barrier = threading.Barrier(2)

        def initiate(amount, key):
            from django.db import close_old_connections

            close_old_connections()
            client = IdempotentTestAPIClient()
            client.force_authenticate(self.tenant_user)
            barrier.wait(timeout=10)
            try:
                response = client.post('/api/v1/billing/mpesa/initiate/', {
                    'amount_cents': amount,
                    'idempotency_key': key,
                }, format='json')
                return response.status_code
            finally:
                connection.close()

        with patch('application.services.mpesa.MpesaClient.from_settings', return_value=fake):
            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(
                    lambda args: initiate(*args),
                    (
                        (100000, '4a9f3700-87eb-4e5a-81d8-dfc1fe39a001'),
                        (60000, '4a9f3700-87eb-4e5a-81d8-dfc1fe39a002'),
                    ),
                ))

        self.assertEqual(sorted(statuses), [status.HTTP_202_ACCEPTED, status.HTTP_400_BAD_REQUEST])
        self.assertEqual(MpesaAttempt.objects.count(), 1)
        self.assertEqual(len(fake.stk_calls), 1)
