from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import MpesaAttempt


class MpesaInitiateSerializer(serializers.Serializer):
    amount_cents = serializers.IntegerField(min_value=1)
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=30)
    invoice = serializers.IntegerField(required=False, min_value=1)
    idempotency_key = serializers.UUIDField()


class MpesaOperatorEvidenceSerializer(serializers.Serializer):
    class EvidenceSource:
        choices = (
            ('SAFARICOM_PORTAL', 'Safaricom portal'),
            ('SAFARICOM_STATEMENT', 'Safaricom statement'),
            ('BANK_STATEMENT', 'Bank statement'),
        )

    evidence_source = serializers.ChoiceField(choices=EvidenceSource.choices)
    evidence_reference = serializers.CharField(min_length=3, max_length=120, trim_whitespace=True)
    receipt = serializers.RegexField(r'^[A-Za-z0-9]{5,64}$', max_length=64, trim_whitespace=True)
    amount_cents = serializers.IntegerField(min_value=1)
    merchant_request_id = serializers.CharField(min_length=1, max_length=64, trim_whitespace=True)
    checkout_request_id = serializers.CharField(min_length=1, max_length=64, trim_whitespace=True)
    account_reference = serializers.CharField(required=False, allow_blank=True, max_length=12, trim_whitespace=True)
    phone_number = serializers.CharField(min_length=9, max_length=15, trim_whitespace=True)
    transaction_date = serializers.DateField()


class MpesaAttemptSerializer(serializers.ModelSerializer):
    accepted = serializers.SerializerMethodField()
    payment_settled = serializers.SerializerMethodField()
    detail = serializers.SerializerMethodField()

    class Meta:
        model = MpesaAttempt
        fields = (
            'id',
            'status',
            'accepted',
            'payment_settled',
            'amount_cents',
            'currency',
            'phone_number',
            'invoice',
            'merchant_request_id',
            'checkout_request_id',
            'response_code',
            'response_description',
            'customer_message',
            'created_at',
            'detail',
        )
        read_only_fields = fields

    def get_accepted(self, obj):
        return obj.status == MpesaAttempt.Status.STK_SENT

    def get_payment_settled(self, obj):
        return obj.status == MpesaAttempt.Status.SUCCESS

    def get_detail(self, obj):
        if obj.status == MpesaAttempt.Status.STK_SENT:
            return (
                'STK Push accepted for processing. '
                'This is not payment success; settlement waits for the M-Pesa callback.'
            )
        if obj.status == MpesaAttempt.Status.SUCCESS:
            return 'M-Pesa payment settled onto the canonical ledger.'
        if obj.status == MpesaAttempt.Status.FAILED:
            return 'M-Pesa did not complete the payment. No payment was recorded.'
        if obj.status in (MpesaAttempt.Status.CANCELLED, MpesaAttempt.Status.TIMEOUT):
            return 'M-Pesa did not complete the payment. No payment was recorded.'
        return 'M-Pesa payment attempt is processing.'


class MpesaAttemptStatusSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    receipt = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()

    class Meta:
        model = MpesaAttempt
        fields = ('id', 'status', 'amount_cents', 'currency', 'receipt', 'created_at', 'message')
        read_only_fields = fields

    def get_status(self, obj):
        if obj.status == MpesaAttempt.Status.SUCCESS:
            return 'SUCCESSFUL'
        if obj.status == MpesaAttempt.Status.CANCELLED:
            return 'CANCELLED'
        if obj.status == MpesaAttempt.Status.FAILED:
            return 'FAILED'
        if obj.status == MpesaAttempt.Status.TIMEOUT:
            return 'EXPIRED'
        if obj.reconciliation_state in (
            MpesaAttempt.ReconciliationState.UNRESOLVED,
            MpesaAttempt.ReconciliationState.SUCCESS_NEEDS_RECEIPT,
            MpesaAttempt.ReconciliationState.EXHAUSTED,
        ):
            return 'UNRESOLVED'
        if obj.status in (MpesaAttempt.Status.INITIATED, MpesaAttempt.Status.STK_SENT) and obj.created_at < timezone.now() - timedelta(minutes=2):
            return 'UNRESOLVED'
        return 'PENDING'

    def get_receipt(self, obj):
        if obj.status == MpesaAttempt.Status.SUCCESS:
            return obj.mpesa_receipt_number
        return None

    def get_message(self, obj):
        status_value = self.get_status(obj)
        if status_value == 'SUCCESSFUL':
            return 'M-Pesa confirmed the payment and it is recorded in your rent ledger.'
        if status_value == 'CANCELLED':
            return 'The M-Pesa payment prompt was cancelled. No payment was recorded.'
        if status_value == 'FAILED':
            return 'M-Pesa did not complete the payment. No payment was recorded.'
        if status_value == 'EXPIRED':
            return 'The payment request expired without a completed payment.'
        if status_value == 'UNRESOLVED':
            return 'No final provider confirmation is available yet. Check this attempt before starting another payment.'
        return 'The M-Pesa prompt is still pending. This is not a confirmed payment.'
