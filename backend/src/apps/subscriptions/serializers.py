from rest_framework import serializers
from django.utils import timezone

from .models import (
    OrganizationSubscription,
    SubscriptionInvoice,
    SubscriptionPaymentAttempt,
    SubscriptionPlan,
)


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ('id', 'code', 'version', 'name', 'description', 'price_minor', 'currency',
                  'setup_fee_minor', 'interval', 'unit_limit', 'entitlements', 'is_custom_pricing')


class PublicSubscriptionPlanSerializer(serializers.ModelSerializer):
    """The safe, read-only subset used by public plan discovery."""
    class Meta:
        model = SubscriptionPlan
        fields = ('code', 'name', 'description', 'price_minor', 'currency',
                  'setup_fee_minor', 'interval', 'unit_limit', 'entitlements', 'is_custom_pricing')


class SubscriptionInvoiceSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    payment_reference = serializers.SerializerMethodField()
    payment_review_status = serializers.SerializerMethodField()
    amount_paid_minor = serializers.SerializerMethodField()
    outstanding_minor = serializers.SerializerMethodField()
    settlement_status = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionInvoice
        fields = ('id', 'invoice_number', 'plan', 'plan_name', 'monthly_fee_minor', 'setup_fee_minor',
                  'amount_minor', 'amount_paid_minor', 'outstanding_minor', 'currency', 'settlement_status',
                  'period_start', 'period_end', 'issued_at', 'due_date', 'status', 'payment_reference', 'payment_review_status')

    def get_status(self, invoice):
        if invoice.status == SubscriptionInvoice.Status.ISSUED and invoice.due_date < timezone.localdate():
            return SubscriptionInvoice.Status.OVERDUE
        return invoice.status

    def get_payment_reference(self, invoice):
        attempt = invoice.payment_attempts.order_by('-created_at').first()
        return attempt.reference if attempt else None

    def get_payment_review_status(self, invoice):
        attempt = invoice.payment_attempts.order_by('-created_at').first()
        return attempt.status if attempt else None

    def get_amount_paid_minor(self, invoice):
        payment = getattr(invoice, 'payment', None)
        if payment and payment.status == 'VERIFIED':
            return payment.amount_minor
        return 0

    def get_outstanding_minor(self, invoice):
        return max(0, invoice.amount_minor - self.get_amount_paid_minor(invoice))

    def get_settlement_status(self, invoice):
        payment = getattr(invoice, 'payment', None)
        return payment.status if payment else None


class SubscriptionPaymentAttemptSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    amount_minor = serializers.IntegerField(source='invoice.amount_minor', read_only=True)
    currency = serializers.CharField(source='invoice.currency', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    reported_by_name = serializers.CharField(source='reported_by.username', read_only=True)

    class Meta:
        model = SubscriptionPaymentAttempt
        fields = ('id', 'invoice', 'invoice_number', 'organization', 'organization_name', 'amount_minor',
                  'currency', 'reference', 'status', 'reported_by_name', 'created_at')


class OrganizationSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    pending_plan = SubscriptionPlanSerializer(read_only=True)
    unit_count = serializers.IntegerField(read_only=True)
    remaining_units = serializers.IntegerField(read_only=True)
    invoices = SubscriptionInvoiceSerializer(many=True, read_only=True)

    class Meta:
        model = OrganizationSubscription
        fields = ('id', 'organization', 'plan', 'pending_plan', 'status', 'current_period_start',
                  'current_period_end', 'setup_fee_paid', 'setup_fee_invoiced', 'unit_limit_override', 'effective_unit_limit', 'unit_count',
                  'remaining_units', 'effective_entitlements', 'invoices', 'created_at', 'updated_at')
        read_only_fields = fields


class PlanChangeSerializer(serializers.Serializer):
    plan = serializers.SlugField(max_length=32)


class PaymentReportSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=100, trim_whitespace=True)


class PaymentReviewSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=8, max_length=1000, trim_whitespace=True)


class EnterpriseInvoiceSerializer(serializers.Serializer):
    organization = serializers.IntegerField(min_value=1)
    amount_minor = serializers.IntegerField(min_value=1)
    unit_limit = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(min_length=8, max_length=1000, trim_whitespace=True)

