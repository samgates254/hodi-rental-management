import calendar
from datetime import date

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Unit
from application.services.audit import record_audit

from .models import (
    OrganizationSubscription,
    SubscriptionInvoice,
    SubscriptionPayment,
    SubscriptionPaymentAttempt,
    SubscriptionPlan,
)


def rentable_unit_count(organization_id):
    """Count each Unit once; inactive inventory is excluded, tenants/leases are not counted."""
    return Unit.objects.filter(
        building__property__organization_id=organization_id,
    ).exclude(status=Unit.Status.INACTIVE).count()


def lock_subscription(organization_id):
    Organization.objects.select_for_update().get(pk=organization_id)
    return OrganizationSubscription.objects.select_for_update().select_related('plan').get(organization_id=organization_id)


def get_or_create_free_subscription(organization):
    free_plan = SubscriptionPlan.objects.get(code='free', is_active=True)
    subscription, _ = OrganizationSubscription.objects.get_or_create(
        organization=organization,
        defaults={'plan': free_plan, 'status': OrganizationSubscription.Status.FREE},
    )
    return subscription


def ensure_unit_capacity(organization_id, *, counts_as_rentable=True, existing_unit_id=None):
    """Lock the organization and enforce the current plan before adding billable inventory."""
    if not counts_as_rentable:
        return
    with transaction.atomic():
        subscription = lock_subscription(organization_id)
        count = rentable_unit_count(organization_id)
        if existing_unit_id and Unit.objects.filter(
            pk=existing_unit_id,
            building__property__organization_id=organization_id,
        ).exclude(status=Unit.Status.INACTIVE).exists():
            count -= 1
        limit = subscription.effective_unit_limit
        if limit is None:
            return
        if subscription.status in (OrganizationSubscription.Status.PAST_DUE, OrganizationSubscription.Status.GRACE,
                                   OrganizationSubscription.Status.CANCELLED, OrganizationSubscription.Status.EXPIRED):
            raise ValidationError({
                'code': 'SUBSCRIPTION_RESTRICTED',
                'detail': 'This organization cannot add rentable units while its subscription needs attention. Existing records remain available.',
                'current_limit': limit,
                'upgrade_path': '/landlords#subscription',
            })
        if count >= limit:
            raise ValidationError({
                'code': 'UNIT_LIMIT_REACHED',
                'detail': f'This plan includes {limit} rentable units. Upgrade the subscription to add more.',
                'current_units': count,
                'current_limit': limit,
                'upgrade_path': '/landlords#subscription',
            })


def _month_after(value):
    month = value.month % 12 + 1
    year = value.year + (value.month == 12)
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@transaction.atomic
def request_plan_change(*, organization_id, plan_code, actor, request=None):
    subscription = lock_subscription(organization_id)
    plan = SubscriptionPlan.objects.filter(code=plan_code, is_active=True).first()
    if plan is None:
        raise ValidationError({'plan': 'Choose an available subscription plan.'})
    if plan.code == 'free' or plan.is_custom_pricing or plan.price_minor is None:
        raise ValidationError({'plan': 'This plan change requires Hodi assistance. Contact support to proceed.'})
    today = timezone.localdate()
    if (
        plan.pk == subscription.plan_id
        and subscription.status == OrganizationSubscription.Status.ACTIVE
        and subscription.current_period_end
        and subscription.current_period_end > today
    ):
        raise ValidationError({'plan': 'This organization already uses that plan for the current billing period.'})
    if subscription.pending_plan_id and SubscriptionInvoice.objects.filter(
        subscription=subscription, plan=subscription.pending_plan, status=SubscriptionInvoice.Status.ISSUED,
    ).exists():
        raise ValidationError({'plan': 'A plan change invoice is already awaiting payment.'})

    invoice = SubscriptionInvoice.objects.create(
        organization_id=organization_id,
        subscription=subscription,
        plan=plan,
        amount_minor=plan.price_minor + (plan.setup_fee_minor if not subscription.setup_fee_invoiced else 0),
        monthly_fee_minor=plan.price_minor,
        setup_fee_minor=plan.setup_fee_minor if not subscription.setup_fee_invoiced else 0,
        currency=plan.currency,
        period_start=today,
        period_end=_month_after(today),
        due_date=today,
        created_by=actor,
    )
    subscription.pending_plan = plan
    subscription.setup_fee_invoiced = True
    subscription.save(update_fields=('pending_plan', 'setup_fee_invoiced', 'updated_at'))
    record_audit(
        action='subscription.plan_change_requested', object_type='SubscriptionInvoice', object_id=invoice.pk,
        actor=actor, organization=subscription.organization,
        metadata={'from_plan': subscription.plan.code, 'to_plan': plan.code, 'amount_minor': invoice.amount_minor,
                  'monthly_fee_minor': invoice.monthly_fee_minor, 'setup_fee_minor': invoice.setup_fee_minor},
        request=request,
    )
    return invoice


@transaction.atomic
def issue_enterprise_invoice(*, organization_id, amount_minor, unit_limit, actor, reason, request=None):
    if not actor.is_staff:
        raise PermissionDenied('Only an authorized Hodi administrator can configure Enterprise terms.')
    subscription = lock_subscription(organization_id)
    plan = SubscriptionPlan.objects.get(code='enterprise', is_active=True, is_custom_pricing=True)
    if subscription.pending_plan_id:
        raise ValidationError({'plan': 'Resolve the existing pending plan change before configuring Enterprise.'})
    today = timezone.localdate()
    invoice = SubscriptionInvoice.objects.create(
        organization_id=organization_id, subscription=subscription, plan=plan,
        amount_minor=amount_minor + (plan.setup_fee_minor if not subscription.setup_fee_invoiced else 0),
        monthly_fee_minor=amount_minor,
        setup_fee_minor=plan.setup_fee_minor if not subscription.setup_fee_invoiced else 0,
        currency=plan.currency,
        period_start=today, period_end=_month_after(today), due_date=today, created_by=actor,
    )
    subscription.pending_plan = plan
    subscription.pending_unit_limit_override = unit_limit
    subscription.setup_fee_invoiced = True
    subscription.save(update_fields=('pending_plan', 'pending_unit_limit_override', 'setup_fee_invoiced', 'updated_at'))
    record_audit(
        action='subscription.enterprise_terms_issued', object_type='SubscriptionInvoice', object_id=invoice.pk,
        actor=actor, organization=subscription.organization,
        metadata={'amount_minor': invoice.amount_minor, 'monthly_fee_minor': invoice.monthly_fee_minor,
                  'setup_fee_minor': invoice.setup_fee_minor, 'currency': plan.currency, 'unit_limit': unit_limit,
                  'reason': reason.strip()}, request=request,
    )
    return invoice


@transaction.atomic
def report_payment(*, invoice_id, organization_id, actor, reference, request=None):
    invoice = SubscriptionInvoice.objects.select_for_update().filter(
        pk=invoice_id, organization_id=organization_id,
    ).first()
    if invoice is None:
        raise ValidationError({'invoice': 'Subscription invoice not found.'})
    if invoice.status != SubscriptionInvoice.Status.ISSUED:
        raise ValidationError({'invoice': 'This invoice is not awaiting payment.'})
    existing_reference = SubscriptionPaymentAttempt.objects.filter(
        reference=reference.strip(),
    ).exclude(invoice=invoice).first()
    if existing_reference:
        raise ValidationError({'reference': 'This payment reference has already been reported for another invoice.'})
    attempt, created = SubscriptionPaymentAttempt.objects.get_or_create(
        invoice=invoice,
        reference=reference.strip(),
        defaults={'organization_id': organization_id, 'reported_by': actor},
    )
    if not created and attempt.status != SubscriptionPaymentAttempt.Status.PENDING_REVIEW:
        raise ValidationError({'reference': 'This payment reference has already been reviewed.'})
    record_audit(
        action='subscription.payment_reported', object_type='SubscriptionPaymentAttempt', object_id=attempt.pk,
        actor=actor, organization=invoice.organization,
        metadata={'invoice_number': invoice.invoice_number}, request=request,
    )
    return attempt


@transaction.atomic
def confirm_reported_payment(*, attempt_id, actor, reason, request=None):
    if not actor.is_staff:
        raise PermissionDenied('Only an authorized Hodi administrator can verify subscription payments.')
    attempt = SubscriptionPaymentAttempt.objects.select_for_update().select_related('invoice').get(pk=attempt_id)
    invoice = SubscriptionInvoice.objects.select_for_update().select_related('subscription', 'plan').get(pk=attempt.invoice_id)
    subscription = lock_subscription(invoice.organization_id)
    if attempt.status != SubscriptionPaymentAttempt.Status.PENDING_REVIEW:
        raise ValidationError({'attempt': 'This payment report has already been reviewed.'})
    if invoice.status != SubscriptionInvoice.Status.ISSUED:
        raise ValidationError({'invoice': 'Invoice is not awaiting verified payment.'})
    now = timezone.now()
    from_plan = subscription.plan
    from_limit = subscription.effective_unit_limit
    to_limit = subscription.pending_unit_limit_override if invoice.plan.code == 'enterprise' else invoice.plan.unit_limit
    if from_limit is None and to_limit is not None:
        change_direction = 'downgrade'
    elif to_limit is None and from_limit is not None:
        change_direction = 'upgrade'
    elif from_limit is not None and to_limit is not None and to_limit > from_limit:
        change_direction = 'upgrade'
    elif from_limit is not None and to_limit is not None and to_limit < from_limit:
        change_direction = 'downgrade'
    elif invoice.plan.price_minor is not None and from_plan.price_minor is not None and invoice.plan.price_minor > from_plan.price_minor:
        change_direction = 'upgrade'
    elif invoice.plan.price_minor is not None and from_plan.price_minor is not None and invoice.plan.price_minor < from_plan.price_minor:
        change_direction = 'downgrade'
    else:
        change_direction = 'renewal'
    payment = SubscriptionPayment.objects.create(
        invoice=invoice, organization=invoice.organization, attempt=attempt,
        amount_minor=invoice.amount_minor, currency=invoice.currency,
        reference=attempt.reference, confirmed_by=actor, confirmed_at=now,
        verification_reason=reason.strip(),
    )
    SubscriptionInvoice.objects.filter(pk=invoice.pk).update(status=SubscriptionInvoice.Status.PAID)
    SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(
        status=SubscriptionPaymentAttempt.Status.CONFIRMED, review_reason=reason.strip(),
        reviewed_by=actor, reviewed_at=now,
    )
    subscription.plan = invoice.plan
    subscription.pending_plan = None
    subscription.status = OrganizationSubscription.Status.ACTIVE
    # Only a verified invoice that actually contains the one-time fee settles
    # that obligation; monthly-only settlements do not change this state.
    subscription.setup_fee_paid = subscription.setup_fee_paid or invoice.setup_fee_minor > 0
    subscription.current_period_start = invoice.period_start
    subscription.current_period_end = invoice.period_end
    subscription.unit_limit_override = subscription.pending_unit_limit_override if invoice.plan.code == 'enterprise' else None
    subscription.pending_unit_limit_override = None
    subscription.save(update_fields=(
        'plan', 'pending_plan', 'status', 'current_period_start', 'current_period_end',
        'unit_limit_override', 'pending_unit_limit_override', 'setup_fee_paid', 'updated_at',
    ))
    record_audit(
        action='subscription.payment_verified', object_type='SubscriptionPayment', object_id=payment.pk,
        actor=actor, organization=invoice.organization,
        metadata={'invoice_number': invoice.invoice_number, 'amount_minor': payment.amount_minor,
                  'currency': payment.currency, 'reference': payment.reference, 'reason': reason.strip(),
                  'from_plan': from_plan.code, 'to_plan': invoice.plan.code,
                  'change_direction': change_direction},
        request=request,
    )
    return payment


@transaction.atomic
def reject_reported_payment(*, attempt_id, actor, reason, request=None):
    if not actor.is_staff:
        raise PermissionDenied('Only an authorized Hodi administrator can review subscription payments.')
    attempt = SubscriptionPaymentAttempt.objects.select_for_update().select_related('organization').get(pk=attempt_id)
    if attempt.status != SubscriptionPaymentAttempt.Status.PENDING_REVIEW:
        raise ValidationError({'attempt': 'This payment report has already been reviewed.'})
    now = timezone.now()
    SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(
        status=SubscriptionPaymentAttempt.Status.REJECTED, review_reason=reason.strip(),
        reviewed_by=actor, reviewed_at=now,
    )
    record_audit(
        action='subscription.payment_report_rejected', object_type='SubscriptionPaymentAttempt', object_id=attempt.pk,
        actor=actor, organization=attempt.organization,
        metadata={'reason': reason.strip()}, request=request,
    )
    return attempt


@transaction.atomic
def reverse_subscription_payment(*, payment_id, actor, reason, request=None):
    if not actor.is_staff:
        raise PermissionDenied('Only an authorized Hodi administrator can reverse subscription payments.')
    payment = SubscriptionPayment.objects.select_for_update().select_related('invoice', 'organization').get(pk=payment_id)
    if payment.status != SubscriptionPayment.Status.VERIFIED:
        raise ValidationError({'payment': 'Only a verified payment can be reversed.'})
    now = timezone.now()
    SubscriptionPayment.objects.filter(pk=payment.pk).update(
        status=SubscriptionPayment.Status.REVERSED, reversed_by=actor, reversed_at=now,
        reversal_reason=reason.strip(),
    )
    SubscriptionInvoice.objects.filter(pk=payment.invoice_id).update(status=SubscriptionInvoice.Status.OVERDUE)
    subscription = lock_subscription(payment.organization_id)
    subscription.status = OrganizationSubscription.Status.PAST_DUE
    update_fields = ['status', 'updated_at']
    if payment.invoice.setup_fee_minor:
        subscription.setup_fee_paid = False
        update_fields.append('setup_fee_paid')
    subscription.save(update_fields=update_fields)
    record_audit(
        action='subscription.payment_reversed', object_type='SubscriptionPayment', object_id=payment.pk,
        actor=actor, organization=payment.organization,
        metadata={'invoice_number': payment.invoice.invoice_number, 'amount_minor': payment.amount_minor,
                  'currency': payment.currency, 'reason': reason.strip(), 'status': SubscriptionPayment.Status.REVERSED},
        request=request,
    )
    return payment

