import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


SUPPORTED_ENTITLEMENTS = {'reporting', 'billing', 'maintenance', 'staff_management'}


class SubscriptionPlan(models.Model):
    class Interval(models.TextChoices):
        MONTH = 'MONTH', 'Monthly'

    code = models.SlugField(max_length=32)
    version = models.PositiveSmallIntegerField(default=1)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True)
    price_minor = models.PositiveBigIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, default='KES')
    interval = models.CharField(max_length=12, choices=Interval.choices, default=Interval.MONTH)
    unit_limit = models.PositiveIntegerField(null=True, blank=True)
    entitlements = models.JSONField(default=dict, blank=True)
    is_custom_pricing = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('price_minor', 'name', 'version')
        constraints = [
            models.UniqueConstraint(fields=('code', 'version'), name='unique_subscription_plan_version'),
            models.UniqueConstraint(fields=('code',), condition=Q(is_active=True), name='one_active_subscription_plan_code'),
            models.CheckConstraint(
                condition=(Q(is_custom_pricing=True, price_minor__isnull=True) | Q(is_custom_pricing=False, price_minor__isnull=False)),
                name='subscription_plan_price_custom_consistent',
            ),
            models.CheckConstraint(condition=Q(unit_limit__isnull=True) | Q(unit_limit__gt=0), name='subscription_plan_unit_limit_positive'),
        ]

    def clean(self):
        super().clean()
        if self.is_custom_pricing and self.price_minor is not None:
            raise ValidationError({'price_minor': 'Custom-priced plans do not have a catalogue price.'})
        if not isinstance(self.entitlements, dict):
            raise ValidationError({'entitlements': 'Entitlements must be a feature map.'})
        unsupported = set(self.entitlements) - SUPPORTED_ENTITLEMENTS
        if unsupported or any(type(value) is not bool for value in self.entitlements.values()):
            raise ValidationError({'entitlements': 'Use supported feature keys with boolean values.'})
        if self.code == 'enterprise' and self.unit_limit is not None:
            raise ValidationError({'unit_limit': 'Enterprise limits are negotiated per organization.'})

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.get(pk=self.pk)
            immutable = ('code', 'version', 'name', 'description', 'price_minor', 'currency', 'interval', 'unit_limit', 'entitlements', 'is_custom_pricing')
            if any(getattr(original, field) != getattr(self, field) for field in immutable):
                raise ValidationError('Plan terms are versioned. Create a new plan version to change commercial terms.')
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Subscription plans are retained for invoice and entitlement history.')

    def __str__(self):
        return f'{self.name} v{self.version}'


class OrganizationSubscription(models.Model):
    class Status(models.TextChoices):
        FREE = 'FREE', 'Free'
        ACTIVE = 'ACTIVE', 'Active'
        PAST_DUE = 'PAST_DUE', 'Past due'
        GRACE = 'GRACE', 'Grace period'
        CANCELLED = 'CANCELLED', 'Cancelled'
        EXPIRED = 'EXPIRED', 'Expired'

    organization = models.OneToOneField('organizations.Organization', on_delete=models.PROTECT, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='subscriptions')
    pending_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, null=True, blank=True, related_name='pending_subscriptions')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.FREE)
    unit_limit_override = models.PositiveIntegerField(null=True, blank=True)
    pending_unit_limit_override = models.PositiveIntegerField(null=True, blank=True)
    current_period_start = models.DateField(null=True, blank=True)
    current_period_end = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.unit_limit_override is not None and self.unit_limit_override <= 0:
            raise ValidationError({'unit_limit_override': 'Negotiated unit limit must be positive.'})
        if self.pending_unit_limit_override is not None and self.pending_unit_limit_override <= 0:
            raise ValidationError({'pending_unit_limit_override': 'Negotiated unit limit must be positive.'})
        if self.unit_limit_override is not None and self.plan.code != 'enterprise':
            raise ValidationError({'unit_limit_override': 'Only Enterprise subscriptions use negotiated unit limits.'})
        if self.current_period_start and self.current_period_end and self.current_period_end <= self.current_period_start:
            raise ValidationError({'current_period_end': 'Billing period end must follow its start.'})

    @property
    def effective_unit_limit(self):
        return self.unit_limit_override if self.unit_limit_override is not None else self.plan.unit_limit

    @property
    def effective_entitlements(self):
        return self.plan.entitlements

    def __str__(self):
        return f'{self.organization} · {self.plan.name} ({self.status})'


class SubscriptionInvoice(models.Model):
    class Status(models.TextChoices):
        ISSUED = 'ISSUED', 'Issued'
        PAID = 'PAID', 'Paid'
        OVERDUE = 'OVERDUE', 'Overdue'
        VOID = 'VOID', 'Void'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=48, unique=True, editable=False)
    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT, related_name='subscription_invoices')
    subscription = models.ForeignKey(OrganizationSubscription, on_delete=models.PROTECT, related_name='invoices')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='invoices')
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    period_start = models.DateField()
    period_end = models.DateField()
    issued_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ISSUED)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_subscription_invoices')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-issued_at',)
        constraints = [
            models.CheckConstraint(condition=Q(amount_minor__gt=0), name='subscription_invoice_amount_positive'),
            models.CheckConstraint(condition=Q(period_end__gt=models.F('period_start')), name='subscription_invoice_period_valid'),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Issued subscription invoices are immutable; record a separate status transition.')
        if not self.invoice_number:
            self.invoice_number = f'HODI-SUB-{uuid.uuid4().hex[:16].upper()}'
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.invoice_number


class SubscriptionPaymentAttempt(models.Model):
    class Status(models.TextChoices):
        PENDING_REVIEW = 'PENDING_REVIEW', 'Pending verification'
        REJECTED = 'REJECTED', 'Rejected'
        CONFIRMED = 'CONFIRMED', 'Confirmed'

    invoice = models.ForeignKey(SubscriptionInvoice, on_delete=models.PROTECT, related_name='payment_attempts')
    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT, related_name='subscription_payment_attempts')
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='reported_subscription_payments')
    reference = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_REVIEW)
    review_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='reviewed_subscription_payment_attempts')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at',)
        constraints = [
            models.UniqueConstraint(fields=('invoice', 'reference'), name='unique_subscription_attempt_reference'),
            models.UniqueConstraint(fields=('reference',), name='unique_subscription_attempt_payment_reference'),
            models.CheckConstraint(condition=~Q(reference=''), name='subscription_attempt_reference_required'),
        ]


class SubscriptionPayment(models.Model):
    class Status(models.TextChoices):
        VERIFIED = 'VERIFIED', 'Verified'
        REVERSED = 'REVERSED', 'Reversed'

    invoice = models.OneToOneField(SubscriptionInvoice, on_delete=models.PROTECT, related_name='payment')
    organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT, related_name='subscription_payments')
    attempt = models.OneToOneField(SubscriptionPaymentAttempt, on_delete=models.PROTECT, related_name='settlement')
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.VERIFIED)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='confirmed_subscription_payments')
    confirmed_at = models.DateTimeField()
    verification_reason = models.TextField()
    reversed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='reversed_subscription_payments')
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.TextField(blank=True)

    class Meta:
        ordering = ('-confirmed_at',)
        constraints = [models.CheckConstraint(condition=Q(amount_minor__gt=0), name='subscription_payment_amount_positive')]

