from rest_framework import serializers

from apps.leases.models import Lease
from apps.tenants.models import Tenant

from .models import (
    Charge,
    DocumentStatus,
    Invoice,
    LedgerPosting,
    MAX_MONEY_CENTS,
    Payment,
    PaymentAllocation,
    PaymentReversal,
    PaymentReversalAllocation,
)


class ChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Charge
        fields = (
            'id', 'invoice', 'organization', 'tenant', 'charge_type', 'description',
            'amount_cents', 'balance_cents', 'due_date', 'period_start', 'lifecycle',
            'currency', 'created_at', 'updated_at',
        )
        read_only_fields = fields


class ChargeWriteSerializer(serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all())
    charge_type = serializers.CharField()
    amount_cents = serializers.IntegerField(min_value=1, max_value=MAX_MONEY_CENTS)
    due_date = serializers.DateField()
    period_start = serializers.DateField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True)


class InvoiceSerializer(serializers.ModelSerializer):
    charges = ChargeSerializer(many=True, read_only=True)
    paid_cents = serializers.SerializerMethodField()

    def get_paid_cents(self, invoice):
        return sum(
            charge.amount_cents - charge.balance_cents
            for charge in invoice.charges.all()
            if charge.lifecycle == DocumentStatus.POSTED
        )

    class Meta:
        model = Invoice
        fields = (
            'id', 'organization', 'tenant', 'lease', 'period_start', 'period_end',
            'due_date', 'status', 'currency', 'total_cents', 'paid_cents', 'balance_cents', 'notes',
            'charges', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'id', 'organization', 'status', 'currency', 'total_cents', 'paid_cents', 'balance_cents',
            'charges', 'created_at', 'updated_at',
        )


class InvoiceWriteSerializer(serializers.Serializer):
    tenant = serializers.PrimaryKeyRelatedField(queryset=Tenant.objects.all())
    lease = serializers.PrimaryKeyRelatedField(
        queryset=Lease.objects.all(),
        required=False,
        allow_null=True,
    )
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    due_date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True)
    include_rent = serializers.BooleanField(required=False)
    generation_key = serializers.CharField(required=False, allow_blank=False, max_length=160)


class InvoiceUpdateSerializer(serializers.Serializer):
    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False)
    due_date = serializers.DateField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class PaymentAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAllocation
        fields = ('id', 'charge', 'amount_cents', 'policy_id', 'policy_version', 'created_at')
        read_only_fields = fields


class LedgerPostingSerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerPosting
        fields = ('id', 'reversal', 'account', 'direction', 'amount_cents', 'created_at')
        read_only_fields = fields


class PaymentReversalAllocationSerializer(serializers.ModelSerializer):
    original_allocation_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = PaymentReversalAllocation
        fields = ('id', 'original_allocation_id', 'charge', 'amount_cents', 'created_at')
        read_only_fields = fields


class PaymentReversalSerializer(serializers.ModelSerializer):
    allocations = PaymentReversalAllocationSerializer(many=True, read_only=True)
    postings = LedgerPostingSerializer(many=True, read_only=True)

    class Meta:
        model = PaymentReversal
        fields = (
            'id', 'payment', 'authorized_by', 'reason', 'amount_cents', 'status',
            'allocations', 'postings', 'created_at',
        )
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    allocations = PaymentAllocationSerializer(many=True, read_only=True)
    postings = LedgerPostingSerializer(many=True, read_only=True)
    reversal = PaymentReversalSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Payment
        fields = (
            'id', 'organization', 'tenant', 'amount_cents', 'allocated_cents',
            'overpayment_cents', 'received_date', 'execution_timestamp', 'method',
            'status', 'currency', 'reference', 'external_id', 'recorded_by',
            'policy_id', 'policy_version', 'allocations', 'postings', 'reversal',
            'created_at', 'updated_at',
        )
        read_only_fields = fields


class PaymentWriteSerializer(serializers.Serializer):
    tenant = serializers.PrimaryKeyRelatedField(queryset=Tenant.objects.all())
    amount_cents = serializers.IntegerField(min_value=1, max_value=MAX_MONEY_CENTS)
    received_date = serializers.DateField()
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    reference = serializers.CharField(required=False, allow_blank=True)
    external_id = serializers.CharField(required=False, allow_blank=True)

    def validate_method(self, method):
        if method == Payment.Method.MPESA:
            raise serializers.ValidationError(
                'M-Pesa payments are recorded only after verified provider settlement.'
            )
        return method


class ManualReceiptSerializer(serializers.Serializer):
    """A staff-confirmed receipt, settled atomically by the canonical ledger."""

    tenant = serializers.PrimaryKeyRelatedField(queryset=Tenant.objects.all())
    amount_cents = serializers.IntegerField(min_value=1, max_value=MAX_MONEY_CENTS)
    received_date = serializers.DateField()
    method = serializers.ChoiceField(choices=(
        Payment.Method.CASH,
        Payment.Method.BANK_TRANSFER,
        Payment.Method.OTHER,
    ))
    reference = serializers.CharField(min_length=1, max_length=100, trim_whitespace=True)


class AllocateSerializer(serializers.Serializer):
    policy_id = serializers.CharField()
    policy_version = serializers.IntegerField()


class PaymentReversalRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(trim_whitespace=True, allow_blank=False, max_length=2000)
    # Partial reversals are not supported. Supplying an amount makes the
    # full-payment contract explicit and lets the endpoint reject partial asks.
    amount_cents = serializers.IntegerField(required=False, min_value=1, max_value=MAX_MONEY_CENTS)
