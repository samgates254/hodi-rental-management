from rest_framework import serializers

from .models import MpesaAttempt


class MpesaInitiateSerializer(serializers.Serializer):
    amount_cents = serializers.IntegerField(min_value=1)
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=30)
    invoice = serializers.IntegerField(required=False, min_value=1)


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
