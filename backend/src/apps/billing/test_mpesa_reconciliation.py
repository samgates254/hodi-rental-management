from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.billing.models import MpesaAttempt, Payment
from apps.organizations.models import Organization
from apps.tenants.models import Tenant
from infrastructure.payments.mpesa import MpesaHTTPError, MpesaTimeoutError
from django.contrib.auth import get_user_model


@override_settings(
    MPESA_BASE_URL='https://sandbox.safaricom.co.ke', MPESA_CONSUMER_KEY='test-key',
    MPESA_CONSUMER_SECRET='test-secret', MPESA_SHORTCODE='123456', MPESA_PASSKEY='test-passkey',
    MPESA_CALLBACK_URL='https://example.test/callback/token', MPESA_CALLBACK_AUTH_TOKEN='token',
)
class MpesaReconciliationCommandTests(TestCase):
    def setUp(self):
        actor = get_user_model().objects.create_user(username='reconcile-tenant')
        organization = Organization.objects.create(name='Reconciliation Homes')
        tenant = Tenant.objects.create(
            organization=organization, user=actor, first_name='Test', last_name='Tenant',
            phone_number='+254700000010',
        )
        self.attempt = MpesaAttempt.objects.create(
            organization=organization, tenant=tenant, initiated_by=actor,
            amount_cents=150000, phone_number='254700000010',
            status=MpesaAttempt.Status.STK_SENT,
            merchant_request_id='merchant-1', checkout_request_id='checkout-1',
            created_at=timezone.now() - timedelta(minutes=10),
        )
        MpesaAttempt.objects.filter(pk=self.attempt.pk).update(
            created_at=timezone.now() - timedelta(minutes=10),
        )
        self.attempt.refresh_from_db()

    def query_result(self, result_code, **overrides):
        result = {
            'ResponseCode': '0', 'ResultCode': result_code,
            'CheckoutRequestID': self.attempt.checkout_request_id,
            'MerchantRequestID': self.attempt.merchant_request_id,
            'ResultDesc': 'Provider result',
        }
        result.update(overrides)
        return result

    def run_command(self, *args):
        output = StringIO()
        call_command('reconcile_mpesa_attempts', *args, stdout=output)
        return output.getvalue()

    def test_dry_run_never_calls_provider(self):
        with patch('infrastructure.payments.mpesa.MpesaClient.stk_query') as query:
            output = self.run_command('--dry-run')
        query.assert_not_called()
        self.assertIn('1 stale M-Pesa attempt(s) eligible', output)

    def test_provider_success_is_not_posted_without_receipt_metadata(self):
        with patch('infrastructure.payments.mpesa.MpesaClient.stk_query', return_value=self.query_result('0')):
            self.run_command()
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.STK_SENT)
        self.assertEqual(self.attempt.reconciliation_state, MpesaAttempt.ReconciliationState.SUCCESS_NEEDS_RECEIPT)
        self.assertEqual(self.attempt.reconciliation_attempts, 1)
        self.assertEqual(Payment.objects.count(), 0)
        audit = AuditLog.objects.get(action='mpesa.stk.reconcile')
        self.assertTrue(audit.metadata['review_required'])

    def test_provider_failure_closes_only_matching_attempt(self):
        with patch('infrastructure.payments.mpesa.MpesaClient.stk_query', return_value=self.query_result('1032')):
            self.run_command()
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.CANCELLED)
        self.assertEqual(self.attempt.reconciliation_state, MpesaAttempt.ReconciliationState.PROVIDER_FAILED)
        self.assertEqual(Payment.objects.count(), 0)

    def test_query_http_500_keeps_attempt_unresolved_and_retryable(self):
        with patch('infrastructure.payments.mpesa.MpesaClient.stk_query', side_effect=MpesaHTTPError('Daraja request failed.')) as query:
            self.run_command()
            self.attempt.refresh_from_db()
            self.assertEqual(self.attempt.status, MpesaAttempt.Status.STK_SENT)
            self.assertEqual(self.attempt.reconciliation_state, MpesaAttempt.ReconciliationState.UNRESOLVED)
            self.assertEqual(self.attempt.reconciliation_attempts, 1)

            # Backoff prevents an immediate duplicate request. A later retry
            # can query again without creating a second payment attempt/posting.
            self.run_command()
            query.assert_called_once()
            MpesaAttempt.objects.filter(pk=self.attempt.pk).update(
                last_reconciliation_at=timezone.now() - timedelta(minutes=3),
            )
            query.side_effect = None
            query.return_value = self.query_result('1032')
            self.run_command()

        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.CANCELLED)
        self.assertEqual(self.attempt.reconciliation_attempts, 2)
        self.assertEqual(Payment.objects.count(), 0)

    def test_malformed_query_responses_remain_unresolved(self):
        malformed = [
            None,
            {'ResponseCode': '0', 'ResultCode': '1032'},
            self.query_result('1032', ResultDesc=''),
            self.query_result('1032', MerchantRequestID=''),
        ]
        for response in malformed:
            with self.subTest(response=response):
                MpesaAttempt.objects.filter(pk=self.attempt.pk).update(
                    status=MpesaAttempt.Status.STK_SENT,
                    reconciliation_state=MpesaAttempt.ReconciliationState.UNRESOLVED,
                    reconciliation_attempts=0,
                    last_reconciliation_at=None,
                )
                with patch('infrastructure.payments.mpesa.MpesaClient.stk_query', return_value=response):
                    self.run_command()
                self.attempt.refresh_from_db()
                self.assertEqual(self.attempt.status, MpesaAttempt.Status.STK_SENT)
                self.assertEqual(self.attempt.reconciliation_state, MpesaAttempt.ReconciliationState.UNRESOLVED)
                self.assertEqual(Payment.objects.count(), 0)

    def test_unknown_nonzero_result_code_is_not_treated_as_terminal_failure(self):
        # Query acceptance is not an outcome, and an undocumented/processing
        # result code is not enough for HODI to close an attempt.
        with patch('infrastructure.payments.mpesa.MpesaClient.stk_query', return_value=self.query_result('4999')):
            self.run_command()
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.STK_SENT)
        self.assertEqual(self.attempt.reconciliation_state, MpesaAttempt.ReconciliationState.UNRESOLVED)
        self.assertEqual(Payment.objects.count(), 0)

    def test_transport_error_is_audited_and_retryable(self):
        with patch('infrastructure.payments.mpesa.MpesaClient.stk_query', side_effect=MpesaTimeoutError('timeout')):
            self.run_command()
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.STK_SENT)
        self.assertEqual(self.attempt.reconciliation_state, MpesaAttempt.ReconciliationState.UNRESOLVED)
        self.assertEqual(self.attempt.reconciliation_attempts, 1)

    def test_retry_limit_excludes_exhausted_attempt_from_provider_queries(self):
        MpesaAttempt.objects.filter(pk=self.attempt.pk).update(
            reconciliation_attempts=5,
            reconciliation_state=MpesaAttempt.ReconciliationState.EXHAUSTED,
            last_reconciliation_at=timezone.now() - timedelta(hours=1),
        )
        with patch('infrastructure.payments.mpesa.MpesaClient.stk_query') as query:
            output = self.run_command()
            query.assert_not_called()

        review = self.run_command('--review-required')
        self.assertIn('1 attempt(s) require operator review', review)
        self.assertIn('EXHAUSTED', review)
        self.assertIn('UNRESOLVED=0', output)

    def test_mismatched_query_references_remain_unresolved(self):
        with patch('infrastructure.payments.mpesa.MpesaClient.stk_query', return_value=self.query_result(
            '1032', CheckoutRequestID='other-checkout',
        )):
            self.run_command()
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.STK_SENT)
        self.assertEqual(self.attempt.reconciliation_state, MpesaAttempt.ReconciliationState.UNRESOLVED)
