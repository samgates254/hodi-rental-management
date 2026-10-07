import threading
import time

from django.contrib.auth import get_user_model
from django.db import OperationalError, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.audit.models import AuditLog
from apps.billing.models import (
    Charge,
    DocumentStatus,
    Invoice,
    LedgerPosting,
    MpesaAttempt,
    Payment,
    PaymentAllocation,
)
from apps.notifications.models import Notification
from apps.organizations.models import Organization
from apps.tenants.models import Tenant

CALLBACK_URL = '/api/v1/billing/mpesa/callback/'
STATEMENT_URL = '/api/v1/billing/statements/me/'

MPESA_SETTINGS = dict(
    MPESA_BASE_URL='https://sandbox.safaricom.co.ke',
    MPESA_CONSUMER_KEY='test-key',
    MPESA_CONSUMER_SECRET='test-consumer-secret-do-not-log',
    MPESA_SHORTCODE='123456',
    MPESA_PASSKEY='test-passkey-do-not-log',
    MPESA_CALLBACK_URL='https://example.test/api/v1/billing/mpesa/callback/',
    MPESA_CALLBACK_AUTH_TOKEN='',
    MPESA_TIMEOUT_SECONDS=5,
    MPESA_TRANSACTION_TYPE='CustomerPayBillOnline',
)


def stk_payload(
    *,
    checkout='ws_CO_1',
    merchant='m-1',
    result_code=0,
    result_desc='The service request is processed successfully.',
    amount=1500,
    receipt='NLJ7RT61SV',
    phone='254700000010',
    transaction_date=20261007120000,
    include_metadata=True,
    extra_body=None,
):
    stk = {
        'MerchantRequestID': merchant,
        'CheckoutRequestID': checkout,
        'ResultCode': result_code,
        'ResultDesc': result_desc,
    }
    if include_metadata:
        stk['CallbackMetadata'] = {
            'Item': [
                {'Name': 'Amount', 'Value': amount},
                {'Name': 'MpesaReceiptNumber', 'Value': receipt},
                {'Name': 'TransactionDate', 'Value': transaction_date},
                {'Name': 'PhoneNumber', 'Value': int(phone) if str(phone).isdigit() else phone},
            ],
        }
    body = {'stkCallback': stk}
    if extra_body:
        body.update(extra_body)
    return {'Body': body}


@override_settings(**MPESA_SETTINGS)
class MpesaCallbackTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.tenant_user = user_model.objects.create_user(username='cb-tenant', password='secret')
        self.other_user = user_model.objects.create_user(username='cb-other', password='secret')
        self.organization = Organization.objects.create(name='Callback Homes')
        self.other_org = Organization.objects.create(name='Other Callback Homes')
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
        today = timezone.localdate()
        self.invoice = Invoice.objects.create(
            organization=self.organization,
            tenant=self.tenant,
            period_start=today.replace(day=1),
            period_end=today,
            due_date=today,
            status=DocumentStatus.POSTED,
            total_cents=150000,
            balance_cents=150000,
        )
        self.charge = Charge.objects.create(
            invoice=self.invoice,
            organization=self.organization,
            tenant=self.tenant,
            charge_type='RENT',
            description='October rent',
            amount_cents=150000,
            balance_cents=150000,
            due_date=today,
            lifecycle=DocumentStatus.POSTED,
        )
        self.attempt = MpesaAttempt.objects.create(
            organization=self.organization,
            tenant=self.tenant,
            invoice=self.invoice,
            initiated_by=self.tenant_user,
            amount_cents=150000,
            phone_number='254700000010',
            status=MpesaAttempt.Status.STK_SENT,
            merchant_request_id='m-1',
            checkout_request_id='ws_CO_1',
            account_reference=str(self.invoice.pk)[:12],
        )

    def post_callback(self, payload, url=CALLBACK_URL, **kwargs):
        return self.client.post(url, payload, format='json', **kwargs)

    def test_valid_success_settles_ledger_and_statement(self):
        today = timezone.localdate()
        txn = int(f'{today:%Y%m%d}120000')
        response = self.post_callback(stk_payload(transaction_date=txn))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['settled'])
        self.assertFalse(response.data['duplicate'])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.SUCCESS)
        self.assertEqual(self.attempt.mpesa_receipt_number, 'NLJ7RT61SV')
        self.assertEqual(self.attempt.result_code, '0')
        payment = Payment.objects.get()
        self.assertEqual(payment.tenant_id, self.tenant.pk)
        self.assertEqual(payment.organization_id, self.organization.pk)
        self.assertEqual(payment.amount_cents, 150000)
        self.assertEqual(payment.method, Payment.Method.MPESA)
        self.assertEqual(payment.status, Payment.Status.ALLOCATED)
        self.assertEqual(payment.external_id, 'NLJ7RT61SV')
        self.assertEqual(payment.reference, 'NLJ7RT61SV')
        self.assertEqual(payment.currency, 'KES')
        self.assertEqual(PaymentAllocation.objects.count(), 1)
        self.assertGreater(LedgerPosting.objects.count(), 0)
        self.assertFalse(LedgerPosting.objects.filter(account='2030').exists())
        self.charge.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.charge.balance_cents, 0)
        self.assertEqual(self.invoice.balance_cents, 0)
        self.assertTrue(AuditLog.objects.filter(action='payment.record').exists())
        self.assertTrue(AuditLog.objects.filter(action='payment.allocate').exists())
        self.assertTrue(AuditLog.objects.filter(action='mpesa.stk.settle').exists())
        self.assertTrue(Notification.objects.filter(
            user=self.tenant_user,
            type='PAYMENT_RECEIVED',
        ).exists())
        self.client.force_authenticate(self.tenant_user)
        statement = self.client.get(STATEMENT_URL)
        self.assertEqual(statement.status_code, status.HTTP_200_OK)
        credits = [row for row in statement.data['lines'] if row['kind'] == 'payment']
        self.assertEqual(len(credits), 1)
        self.assertEqual(credits[0]['credit_cents'], 150000)
        self.assertEqual(statement.data['outstanding_cents'], 0)

    def test_valid_failure_creates_no_payment(self):
        payload = stk_payload(
            result_code=1032,
            result_desc='Request cancelled by user',
            include_metadata=False,
        )
        response = self.post_callback(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['settled'])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.CANCELLED)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(PaymentAllocation.objects.count(), 0)
        self.assertEqual(LedgerPosting.objects.count(), 0)
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.balance_cents, 150000)

    def test_timeout_result_code(self):
        response = self.post_callback(stk_payload(
            result_code=1037,
            result_desc='DS timeout',
            include_metadata=False,
        ))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.TIMEOUT)
        self.assertEqual(Payment.objects.count(), 0)

    def test_generic_nonzero_result_is_failed(self):
        response = self.post_callback(stk_payload(
            result_code=2001,
            result_desc='Wrong PIN',
            include_metadata=False,
        ))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.FAILED)
        self.assertEqual(Payment.objects.count(), 0)

    def test_malformed_body_rejected(self):
        response = self.post_callback({'hello': 'world'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Payment.objects.count(), 0)

    def test_missing_stk_callback_rejected(self):
        response = self.post_callback({'Body': {}})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_checkout_id_rejected(self):
        payload = stk_payload()
        del payload['Body']['stkCallback']['CheckoutRequestID']
        response = self.post_callback(payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Payment.objects.count(), 0)

    def test_missing_result_code_rejected(self):
        payload = stk_payload()
        del payload['Body']['stkCallback']['ResultCode']
        response = self.post_callback(payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_checkout_does_not_create_payment(self):
        payload = stk_payload(checkout='ws_CO_unknown')
        response = self.post_callback(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['matched'])
        self.assertFalse(response.data['settled'])
        self.assertEqual(response.data['status'], 'UNMATCHED')
        self.assertEqual(Payment.objects.count(), 0)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.STK_SENT)
        self.assertTrue(AuditLog.objects.filter(action='mpesa.stk.unmatched').exists())

    def test_wrong_amount_does_not_settle(self):
        response = self.post_callback(stk_payload(amount=1))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['settled'])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.FAILED)
        self.assertEqual(Payment.objects.count(), 0)

    def test_wrong_phone_does_not_settle(self):
        response = self.post_callback(stk_payload(phone='254711111111'))
        self.assertFalse(response.data['settled'])
        self.assertEqual(Payment.objects.count(), 0)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.FAILED)

    def test_missing_receipt_does_not_settle(self):
        payload = stk_payload()
        payload['Body']['stkCallback']['CallbackMetadata']['Item'] = [
            {'Name': 'Amount', 'Value': 1500},
            {'Name': 'PhoneNumber', 'Value': 254700000010},
        ]
        response = self.post_callback(payload)
        self.assertFalse(response.data['settled'])
        self.assertEqual(Payment.objects.count(), 0)

    def test_correct_phone_aliases_match(self):
        response = self.post_callback(stk_payload(phone='0700000010'))
        self.assertTrue(response.data['settled'])
        self.assertEqual(Payment.objects.count(), 1)

    def test_duplicate_callback_is_idempotent(self):
        first = self.post_callback(stk_payload())
        second = self.post_callback(stk_payload())
        third = self.post_callback(stk_payload())
        self.assertTrue(first.data['settled'])
        self.assertTrue(second.data['duplicate'])
        self.assertTrue(third.data['duplicate'])
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(PaymentAllocation.objects.count(), 1)
        self.assertEqual(MpesaAttempt.objects.filter(status=MpesaAttempt.Status.SUCCESS).count(), 1)
        self.assertEqual(Notification.objects.filter(type='PAYMENT_RECEIVED').count(), 1)

    def test_duplicate_receipt_on_second_attempt_does_not_pay_twice(self):
        self.post_callback(stk_payload())
        other_attempt = MpesaAttempt.objects.create(
            organization=self.organization,
            tenant=self.tenant,
            initiated_by=self.tenant_user,
            amount_cents=150000,
            phone_number='254700000010',
            status=MpesaAttempt.Status.STK_SENT,
            merchant_request_id='m-2',
            checkout_request_id='ws_CO_2',
        )
        response = self.post_callback(stk_payload(checkout='ws_CO_2', merchant='m-2'))
        self.assertFalse(response.data['settled'])
        other_attempt.refresh_from_db()
        self.assertEqual(other_attempt.status, MpesaAttempt.Status.FAILED)
        self.assertEqual(Payment.objects.count(), 1)

    def test_callback_cannot_override_tenant_or_organization(self):
        payload = stk_payload()
        payload['tenant'] = self.other_tenant.pk
        payload['organization'] = self.other_org.pk
        payload['tenant_id'] = self.other_tenant.pk
        payload['Body']['tenant'] = self.other_tenant.pk
        response = self.post_callback(payload)
        self.assertTrue(response.data['settled'])
        payment = Payment.objects.get()
        self.assertEqual(payment.tenant_id, self.tenant.pk)
        self.assertEqual(payment.organization_id, self.organization.pk)
        self.assertNotEqual(payment.tenant_id, self.other_tenant.pk)

    def test_callback_for_one_checkout_cannot_settle_another_tenant_attempt(self):
        other_attempt = MpesaAttempt.objects.create(
            organization=self.other_org,
            tenant=self.other_tenant,
            initiated_by=self.other_user,
            amount_cents=150000,
            phone_number='254700000099',
            status=MpesaAttempt.Status.STK_SENT,
            merchant_request_id='m-other',
            checkout_request_id='ws_CO_other',
        )
        self.post_callback(stk_payload())
        other_attempt.refresh_from_db()
        self.assertEqual(other_attempt.status, MpesaAttempt.Status.STK_SENT)
        self.assertEqual(Payment.objects.filter(tenant=self.other_tenant).count(), 0)
        self.assertEqual(Payment.objects.filter(tenant=self.tenant).count(), 1)

    def test_no_invoice_uses_canonical_allocation(self):
        self.attempt.invoice = None
        self.attempt.save(update_fields=('invoice',))
        response = self.post_callback(stk_payload())
        self.assertTrue(response.data['settled'])
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.balance_cents, 0)
        self.assertEqual(Payment.objects.get().status, Payment.Status.ALLOCATED)

    def test_overpayment_posts_to_2020(self):
        self.attempt.amount_cents = 200000
        self.attempt.save(update_fields=('amount_cents',))
        response = self.post_callback(stk_payload(amount=2000, receipt='OVERPAY1'))
        self.assertTrue(response.data['settled'])
        payment = Payment.objects.get()
        self.assertGreater(payment.overpayment_cents, 0)
        self.assertTrue(LedgerPosting.objects.filter(account='2020').exists())
        self.assertFalse(LedgerPosting.objects.filter(account='2030').exists())

    def test_secrets_are_not_logged_on_unmatched_callback(self):
        with self.assertLogs('application.services.mpesa_callback', level='WARNING') as captured:
            self.post_callback(stk_payload(checkout='missing-checkout'))
        joined = '\n'.join(captured.output)
        self.assertNotIn('test-passkey-do-not-log', joined)
        self.assertNotIn('test-consumer-secret-do-not-log', joined)

    @override_settings(**{**MPESA_SETTINGS, 'MPESA_CALLBACK_AUTH_TOKEN': 'path-token-secret'})
    def test_callback_token_gate(self):
        denied = self.post_callback(stk_payload())
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Payment.objects.count(), 0)
        allowed = self.post_callback(
            stk_payload(),
            url='/api/v1/billing/mpesa/callback/path-token-secret/',
        )
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertTrue(allowed.data['settled'])


@override_settings(**MPESA_SETTINGS)
class MpesaCallbackConcurrencyTests(TransactionTestCase):
    def setUp(self):
        user_model = get_user_model()
        self.tenant_user = user_model.objects.create_user(username='cb-conc', password='secret')
        self.organization = Organization.objects.create(name='Concurrent Homes')
        self.tenant = Tenant.objects.create(
            organization=self.organization,
            user=self.tenant_user,
            first_name='Amina',
            last_name='Otieno',
            phone_number='+254700000010',
        )
        today = timezone.localdate()
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
        MpesaAttempt.objects.create(
            organization=self.organization,
            tenant=self.tenant,
            invoice=invoice,
            initiated_by=self.tenant_user,
            amount_cents=150000,
            phone_number='254700000010',
            status=MpesaAttempt.Status.STK_SENT,
            merchant_request_id='m-conc',
            checkout_request_id='ws_CO_CONC',
        )
        self.payload = stk_payload(
            checkout='ws_CO_CONC',
            merchant='m-conc',
            receipt='CONCRECEIPT1',
        )

    def _hammer(self, count):
        barrier = threading.Barrier(count, timeout=10)
        errors = []

        def worker():
            try:
                barrier.wait(timeout=10)
                client = APIClient()
                client.raise_request_exception = False
                last_error = None
                for _ in range(12):
                    try:
                        response = client.post(CALLBACK_URL, self.payload, format='json')
                        if response.status_code == 200:
                            return
                        last_error = response.status_code
                    except OperationalError as error:
                        last_error = error
                    time.sleep(0.05)
                errors.append(last_error)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertEqual(errors, [])
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(PaymentAllocation.objects.filter(payment__external_id='CONCRECEIPT1').count(), 1)
        self.assertEqual(
            MpesaAttempt.objects.filter(
                checkout_request_id='ws_CO_CONC',
                status=MpesaAttempt.Status.SUCCESS,
            ).count(),
            1,
        )
        payment = Payment.objects.get()
        self.assertEqual(payment.status, Payment.Status.ALLOCATED)
        self.assertEqual(
            payment.allocated_cents + payment.overpayment_cents,
            payment.amount_cents,
        )

    def test_two_identical_callbacks_simultaneously(self):
        self._hammer(2)

    def test_three_identical_callbacks_simultaneously(self):
        self._hammer(3)
