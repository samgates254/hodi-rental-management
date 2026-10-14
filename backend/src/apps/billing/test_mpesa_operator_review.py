import logging
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.billing.models import (
    Charge, DocumentStatus, Invoice, LedgerPosting, MpesaAttempt, Payment, PaymentAllocation,
)
from apps.billing.logging import MpesaSensitiveLogFilter
from apps.organizations.models import Organization, OrganizationMembership
from apps.tenants.models import Tenant
from common.rental_dates import rental_business_date


CALLBACK_TOKEN = 'operator-review-callback-token'


@override_settings(
    MPESA_CALLBACK_AUTH_TOKEN=CALLBACK_TOKEN,
    MPESA_CALLBACK_URL=f'https://example.test/api/v1/billing/mpesa/callback/{CALLBACK_TOKEN}/',
)
class MpesaOperatorResolutionTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.reviewer = user_model.objects.create_user(username='review-accountant', password='test-password')
        self.tenant_user = user_model.objects.create_user(username='review-tenant', password='test-password')
        self.other_owner = user_model.objects.create_user(username='review-other-owner', password='test-password')
        self.organization = Organization.objects.create(name='Operator Review Homes')
        self.other_organization = Organization.objects.create(name='Other Operator Review Homes')
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.reviewer,
            role=OrganizationMembership.Role.ACCOUNTANT,
        )
        OrganizationMembership.objects.create(
            organization=self.other_organization, user=self.other_owner,
            role=OrganizationMembership.Role.OWNER,
        )
        self.tenant = Tenant.objects.create(
            organization=self.organization, user=self.tenant_user,
            first_name='Review', last_name='Tenant', phone_number='+254700000010',
        )
        today = rental_business_date()
        self.invoice = Invoice.objects.create(
            organization=self.organization, tenant=self.tenant,
            period_start=today.replace(day=1), period_end=today, due_date=today,
            status=DocumentStatus.POSTED, total_cents=150_000, balance_cents=150_000,
        )
        self.charge = Charge.objects.create(
            invoice=self.invoice, organization=self.organization, tenant=self.tenant,
            charge_type='RENT', description='Rent', amount_cents=150_000,
            balance_cents=150_000, due_date=today, lifecycle=DocumentStatus.POSTED,
        )
        self.attempt = MpesaAttempt.objects.create(
            organization=self.organization, tenant=self.tenant, invoice=self.invoice,
            initiated_by=self.tenant_user, amount_cents=150_000, currency='KES',
            phone_number='254700000010', account_reference='INV-REVIEW-1',
            status=MpesaAttempt.Status.STK_SENT, merchant_request_id='merchant-review-1',
            checkout_request_id='checkout-review-1',
            reconciliation_state=MpesaAttempt.ReconciliationState.SUCCESS_NEEDS_RECEIPT,
        )
        AuditLog.objects.create(
            actor=None, organization=self.organization, action='mpesa.stk.reconcile',
            object_type='MpesaAttempt', object_id=str(self.attempt.pk),
            metadata={
                'outcome': 'SUCCESS', 'provider_result_code': '0', 'review_required': True,
            },
        )
        self.today = today
        self.url = reverse('billing:mpesa-attempt-resolve', args=(self.attempt.pk,))
        self.valid_evidence = {
            'evidence_source': 'SAFARICOM_STATEMENT',
            'evidence_reference': 'statement-row-2026-1012-18',
            'receipt': 'QWER123456',
            'amount_cents': 150_000,
            'merchant_request_id': 'merchant-review-1',
            'checkout_request_id': 'checkout-review-1',
            'account_reference': 'INV-REVIEW-1',
            'phone_number': '254700000010',
            'transaction_date': today.isoformat(),
        }

    def resolve(self, evidence=None):
        self.client.force_authenticate(self.reviewer)
        return self.client.post(self.url, self.valid_evidence if evidence is None else evidence, format='json')

    def test_missing_evidence_is_rejected_without_posting(self):
        response = self.resolve({})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Payment.objects.count(), 0)

    def test_review_requires_authorized_organization_billing_staff_and_not_customer(self):
        self.client.force_authenticate(self.other_owner)
        cross_org = self.client.post(self.url, self.valid_evidence, format='json')
        self.assertEqual(cross_org.status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.tenant_user)
        tenant = self.client.post(self.url, self.valid_evidence, format='json')
        self.assertEqual(tenant.status_code, status.HTTP_404_NOT_FOUND)

        OrganizationMembership.objects.create(
            organization=self.organization, user=self.tenant_user,
            role=OrganizationMembership.Role.OWNER,
        )
        tenant_owner = self.client.post(self.url, self.valid_evidence, format='json')
        self.assertEqual(tenant_owner.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Payment.objects.count(), 0)

    def test_evidence_must_match_amount_references_account_and_phone(self):
        bad_values = {
            'amount_cents': 149_900,
            'merchant_request_id': 'other-merchant',
            'checkout_request_id': 'other-checkout',
            'account_reference': 'OTHER-ACCOUNT',
            'phone_number': '254700000099',
        }
        for key, value in bad_values.items():
            with self.subTest(key=key):
                evidence = {**self.valid_evidence, key: value}
                response = self.resolve(evidence)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(Payment.objects.count(), 0)
                self.assertEqual(self.attempt.mpesa_receipt_number, None)

        invalid_receipt = self.resolve({**self.valid_evidence, 'receipt': 'not a receipt'})
        self.assertEqual(invalid_receipt.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Payment.objects.count(), 0)

    def test_invalid_date_can_be_corrected_by_later_authorized_reconciliation(self):
        stale = self.resolve({
            **self.valid_evidence,
            'transaction_date': (self.today - timedelta(days=1)).isoformat(),
        })
        self.assertEqual(stale.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('transaction_date', stale.data)
        self.assertEqual(Payment.objects.count(), 0)

        resolved = self.resolve()
        self.assertEqual(resolved.status_code, status.HTTP_200_OK)
        self.assertTrue(resolved.data['settled'])
        self.assertEqual(Payment.objects.count(), 1)

    def test_successful_resolution_posts_through_ledger_services_and_audits_reviewer_evidence(self):
        response = self.resolve()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['settled'])
        self.assertFalse(response.data['duplicate'])
        payment = Payment.objects.get()
        self.assertEqual(payment.method, Payment.Method.MPESA)
        self.assertEqual(payment.external_id, self.valid_evidence['receipt'])
        self.assertEqual(payment.amount_cents, self.attempt.amount_cents)
        self.assertEqual(payment.status, Payment.Status.ALLOCATED)
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 1)
        self.assertTrue(LedgerPosting.objects.filter(payment=payment).exists())
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, MpesaAttempt.Status.SUCCESS)
        self.assertEqual(self.attempt.reconciliation_state, MpesaAttempt.ReconciliationState.OPERATOR_RESOLVED)
        self.assertEqual(self.attempt.mpesa_receipt_number, self.valid_evidence['receipt'])
        audit = AuditLog.objects.get(action='mpesa.stk.operator_settlement')
        self.assertEqual(audit.actor, self.reviewer)
        self.assertEqual(audit.metadata['evidence_source'], 'SAFARICOM_STATEMENT')
        self.assertEqual(audit.metadata['evidence_reference'], 'statement-row-2026-1012-18')
        self.assertNotIn('receipt', audit.metadata)

    def test_identical_resolution_is_idempotent_and_conflicting_receipt_is_rejected(self):
        first = self.resolve()
        duplicate = self.resolve()
        conflict = self.resolve({**self.valid_evidence, 'receipt': 'DIFF123456'})
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(duplicate.status_code, status.HTTP_200_OK)
        self.assertTrue(duplicate.data['duplicate'])
        self.assertEqual(conflict.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(PaymentAllocation.objects.count(), 1)
        self.assertEqual(LedgerPosting.objects.count(), 2)

    def test_receipt_cannot_be_reused_for_another_attempt(self):
        self.assertEqual(self.resolve().status_code, status.HTTP_200_OK)
        other_attempt = MpesaAttempt.objects.create(
            organization=self.organization, tenant=self.tenant, invoice=self.invoice,
            initiated_by=self.tenant_user, amount_cents=150_000, currency='KES',
            phone_number='254700000010', account_reference='INV-REVIEW-1',
            status=MpesaAttempt.Status.STK_SENT, merchant_request_id='merchant-review-2',
            checkout_request_id='checkout-review-2',
            reconciliation_state=MpesaAttempt.ReconciliationState.SUCCESS_NEEDS_RECEIPT,
        )
        AuditLog.objects.create(
            actor=None, organization=self.organization, action='mpesa.stk.reconcile',
            object_type='MpesaAttempt', object_id=str(other_attempt.pk),
            metadata={'outcome': 'SUCCESS', 'provider_result_code': '0', 'review_required': True},
        )
        self.client.force_authenticate(self.reviewer)
        response = self.client.post(
            reverse('billing:mpesa-attempt-resolve', args=(other_attempt.pk,)),
            {**self.valid_evidence, 'merchant_request_id': 'merchant-review-2',
             'checkout_request_id': 'checkout-review-2'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Payment.objects.count(), 1)

    def test_attempt_without_audited_query_success_cannot_be_settled(self):
        unaudited = MpesaAttempt.objects.create(
            organization=self.organization, tenant=self.tenant, invoice=self.invoice,
            initiated_by=self.tenant_user, amount_cents=150_000, currency='KES',
            phone_number='254700000010', account_reference='INV-REVIEW-1',
            status=MpesaAttempt.Status.STK_SENT, merchant_request_id='merchant-unaudited',
            checkout_request_id='checkout-unaudited',
            reconciliation_state=MpesaAttempt.ReconciliationState.SUCCESS_NEEDS_RECEIPT,
        )
        self.client.force_authenticate(self.reviewer)
        response = self.client.post(
            reverse('billing:mpesa-attempt-resolve', args=(unaudited.pk,)),
            self.valid_evidence, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Payment.objects.count(), 0)

    def callback_payload(self, receipt):
        return {
            'Body': {'stkCallback': {
                'MerchantRequestID': self.attempt.merchant_request_id,
                'CheckoutRequestID': self.attempt.checkout_request_id,
                'ResultCode': 0,
                'ResultDesc': 'The service request is processed successfully.',
                'CallbackMetadata': {'Item': [
                    {'Name': 'Amount', 'Value': 1500},
                    {'Name': 'MpesaReceiptNumber', 'Value': receipt},
                    {'Name': 'TransactionDate', 'Value': int(f'{self.today:%Y%m%d}120000')},
                    {'Name': 'PhoneNumber', 'Value': 254700000010},
                ]},
            }},
        }

    def test_late_callback_after_manual_resolution_is_duplicate_or_conflict_not_second_posting(self):
        self.assertEqual(self.resolve().status_code, status.HTTP_200_OK)
        with self.assertNoLogs('apps.billing.views_mpesa', level='INFO'):
            with self.assertNoLogs('application.services.mpesa_callback', level='INFO'):
                with patch('apps.billing.views_mpesa.MpesaClient.stk_query', return_value={
                    'ResponseCode': '0', 'ResultCode': '0',
                    'CheckoutRequestID': self.attempt.checkout_request_id,
                    'MerchantRequestID': self.attempt.merchant_request_id,
                    'ResultDesc': 'Provider transaction result',
                }) as query:
                    duplicate = self.client.post(
                        f'/api/v1/billing/mpesa/callback/{CALLBACK_TOKEN}/',
                        self.callback_payload('QWER123456'), format='json',
                    )
                    conflict = self.client.post(
                        f'/api/v1/billing/mpesa/callback/{CALLBACK_TOKEN}/',
                        self.callback_payload('OTHER123456'), format='json',
                    )
        self.assertEqual(query.call_count, 2)
        self.assertTrue(duplicate.data['duplicate'])
        self.assertFalse(conflict.data['settled'])
        self.assertEqual(conflict.data['status'], 'UNRESOLVED')
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(PaymentAllocation.objects.count(), 1)

    def test_invalid_callback_token_is_not_written_to_application_logs(self):
        with self.assertLogs('apps.billing.views_mpesa', level='WARNING') as captured:
            response = self.client.post(
                '/api/v1/billing/mpesa/callback/wrong-token/', {}, format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn(CALLBACK_TOKEN, '\n'.join(captured.output))
        self.assertNotIn('wrong-token', '\n'.join(captured.output))
        self.assertNotIn('/mpesa/callback/', '\n'.join(captured.output))

    def test_mpesa_log_filter_redacts_callback_paths_credentials_phones_and_payloads(self):
        with override_settings(
            MPESA_CONSUMER_SECRET='consumer-secret-test', MPESA_PASSKEY='passkey-test',
        ):
            filter_instance = MpesaSensitiveLogFilter()
            with patch.dict('os.environ', {'DATABASE_URL': 'postgres://test-user:db-secret@example.invalid/hodi'}):
                record = logging.LogRecord(
                    'django.request', logging.ERROR, '', 0,
                    'request /api/v1/billing/mpesa/callback/%s/ phone 254700000010 '
                    'consumer-secret-test passkey-test postgres://test-user:db-secret@example.invalid/hodi',
                    (CALLBACK_TOKEN,), None,
                )
                filter_instance.filter(record)
            self.assertNotIn(CALLBACK_TOKEN, record.getMessage())
            self.assertNotIn('254700000010', record.getMessage())
            self.assertNotIn('consumer-secret-test', record.getMessage())
            self.assertNotIn('passkey-test', record.getMessage())
            self.assertNotIn('db-secret', record.getMessage())
            payload_record = logging.LogRecord(
                'django.request', logging.ERROR, '', 0,
                'CallbackMetadata MpesaReceiptNumber=QWER123456 PhoneNumber=254700000010', (), None,
            )
            filter_instance.filter(payload_record)
            self.assertNotIn('QWER123456', payload_record.getMessage())
            self.assertNotIn('254700000010', payload_record.getMessage())

    def test_ambiguous_provider_result_never_posts_payment(self):
        self.attempt.reconciliation_state = MpesaAttempt.ReconciliationState.UNRESOLVED
        self.attempt.save(update_fields=('reconciliation_state',))
        response = self.resolve()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(PaymentAllocation.objects.count(), 0)
