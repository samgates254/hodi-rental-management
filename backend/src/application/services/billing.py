from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.billing.models import (
    CHARGE_TYPES,
    Charge,
    DEPOSIT_CHARGE_TYPES,
    DocumentStatus,
    Invoice,
    LedgerPosting,
    Payment,
    PaymentAllocation,
    PaymentReversal,
    PaymentReversalAllocation,
)
from apps.leases.models import RentSchedule
from application.services.audit import record_audit
from application.services.notifications import notify_user
from engines.allocation.facade import AllocationCharge, allocate
from engines.proration.facade import prorate_move_in
from rental_os.algorithms.allocation import AllocationError
from rental_os.algorithms.money import MoneyError
from rental_os.algorithms.proration import ProrationError


def _utc_stamp(moment):
    from datetime import timezone as datetime_timezone

    moment = moment.astimezone(datetime_timezone.utc)
    return moment.strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def recompute_invoice_totals(invoice):
    charges = list(invoice.charges.all())
    active = [charge for charge in charges if charge.lifecycle not in (
        DocumentStatus.VOIDED,
        DocumentStatus.WRITTEN_OFF,
    )]
    invoice.total_cents = sum(charge.amount_cents for charge in active)
    invoice.balance_cents = sum(
        charge.balance_cents
        for charge in charges
        if charge.lifecycle == DocumentStatus.POSTED
    )
    invoice.save(update_fields=('total_cents', 'balance_cents', 'updated_at'))
    return invoice


def rent_charge_amount(lease, period_start, period_end):
    schedule = (
        RentSchedule.objects.filter(lease=lease, effective_from__lte=period_start)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=period_start))
        .order_by('-effective_from')
        .first()
    )
    amount = schedule.amount_minor if schedule is not None else lease.monthly_rent_minor
    covers_move_in = period_start <= lease.start_date <= period_end
    if covers_move_in and lease.start_date.day != 1:
        try:
            amount = prorate_move_in(amount, lease.start_date).charge_cents
        except (ProrationError, MoneyError) as error:
            raise ValidationError({'lease': str(error)}) from error
    return amount


@transaction.atomic
def create_invoice(
	*, tenant, period_start, period_end, due_date, actor, lease=None,
	notes='', include_rent=None, generation_key='', request=None,
):
    if period_end < period_start:
        raise ValidationError({'period_end': 'Period end must be on or after period start.'})
    if lease is not None and lease.tenant_id != tenant.pk:
        raise ValidationError({'lease': 'Lease does not belong to this tenant.'})
    if lease is not None and lease.organization_id != tenant.organization_id:
        raise ValidationError({'lease': 'Lease and tenant must belong to the same organization.'})
    if include_rent is None:
        include_rent = lease is not None
    if include_rent and lease is None:
        raise ValidationError({'lease': 'A lease is required to generate a rent charge.'})
    if include_rent and not generation_key:
        generation_key = f'rent:{lease.pk}:{period_start.isoformat()}:{period_end.isoformat()}'
    generation_key = (generation_key or '').strip()
    if len(generation_key) > 160:
        raise ValidationError({'generation_key': 'Must be 160 characters or fewer.'})
    amount = rent_charge_amount(lease, period_start, period_end) if include_rent else None
    if include_rent and amount <= 0:
        raise ValidationError({'lease': 'Rent charge amount must be greater than zero.'})
    if generation_key:
        existing = Invoice.objects.filter(organization=tenant.organization, generation_key=generation_key).first()
        if existing is not None:
            if (existing.tenant_id != tenant.pk or existing.lease_id != getattr(lease, 'pk', None)
                    or existing.period_start != period_start or existing.period_end != period_end):
                raise ValidationError({'generation_key': 'This key was already used for a different billing event.'})
            return existing
    try:
        with transaction.atomic():
            invoice = Invoice.objects.create(
                organization=tenant.organization, tenant=tenant, lease=lease,
                period_start=period_start, period_end=period_end, due_date=due_date,
                notes=notes or '', currency='KES', generation_key=generation_key,
            )
            if include_rent:
                Charge.objects.create(
                    invoice=invoice, organization=tenant.organization, tenant=tenant,
                    charge_type='RENT', description=f'Rent {period_start.isoformat()} to {period_end.isoformat()}',
                    amount_cents=amount, balance_cents=amount, due_date=due_date,
                    period_start=period_start, lifecycle=DocumentStatus.DRAFT, currency='KES',
                )
            recompute_invoice_totals(invoice)
        return invoice
    except IntegrityError:
        existing = Invoice.objects.filter(organization=tenant.organization, generation_key=generation_key).first()
        if existing is not None:
            if (existing.tenant_id == tenant.pk and existing.lease_id == getattr(lease, 'pk', None)
                    and existing.period_start == period_start and existing.period_end == period_end):
                return existing
            raise ValidationError({'generation_key': 'This key was already used for a different billing event.'})
        raise

@transaction.atomic
def add_charge(*, invoice, charge_type, amount_cents, due_date, actor, period_start=None, description=''):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != DocumentStatus.DRAFT:
        raise ValidationError({'invoice': 'Charges can only be added to a draft invoice.'})
    normalized = (charge_type or '').strip().upper()
    if normalized not in CHARGE_TYPES:
        raise ValidationError({'charge_type': 'Unknown charge type.'})
    if normalized in DEPOSIT_CHARGE_TYPES:
        raise ValidationError({
            'charge_type': 'Security deposits must use the separate deposit workflow, not a rent invoice.',
        })
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ValidationError({'amount_cents': 'Amount must be a positive integer number of cents.'})
    charge = Charge.objects.create(
        invoice=invoice,
        organization=invoice.organization,
        tenant=invoice.tenant,
        charge_type=normalized,
        description=description or '',
        amount_cents=amount_cents,
        balance_cents=amount_cents,
        due_date=due_date,
        period_start=period_start,
        lifecycle=DocumentStatus.DRAFT,
        currency='KES',
    )
    recompute_invoice_totals(invoice)
    return charge


@transaction.atomic
def update_draft_invoice(invoice, *, validated_data):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != DocumentStatus.DRAFT:
        raise ValidationError({'status': 'Only draft invoices can be edited.'})
    if invoice.generation_key.startswith('rent:') and any(
        field in validated_data and validated_data[field] != getattr(invoice, field)
        for field in ('period_start', 'period_end')
    ):
        raise ValidationError({
            'period': 'Generated rent periods cannot be changed; create a separate adjustment invoice.',
        })
    for field in ('period_start', 'period_end', 'due_date', 'notes'):
        if field in validated_data:
            setattr(invoice, field, validated_data[field])
    if invoice.period_end < invoice.period_start:
        raise ValidationError({'period_end': 'Period end must be on or after period start.'})
    invoice.save()
    return invoice


@transaction.atomic
def post_invoice(invoice, *, actor, request=None):
    invoice = Invoice.objects.select_for_update(
        of=('self', 'tenant', 'organization'),
    ).select_related('tenant', 'tenant__user', 'organization').get(pk=invoice.pk)
    if invoice.status != DocumentStatus.DRAFT:
        raise ValidationError({'status': 'Only a draft invoice can be posted.'})
    charges = list(invoice.charges.select_for_update().all())
    if not charges:
        raise ValidationError({'charges': 'Add at least one charge before posting.'})
    for charge in charges:
        if charge.lifecycle != DocumentStatus.DRAFT:
            raise ValidationError({'charges': 'Every charge must still be a draft.'})
        charge.lifecycle = DocumentStatus.POSTED
        charge.balance_cents = charge.amount_cents
        charge.save(update_fields=('lifecycle', 'balance_cents', 'updated_at'))
    invoice.status = DocumentStatus.POSTED
    invoice.save(update_fields=('status', 'updated_at'))
    recompute_invoice_totals(invoice)
    record_audit(
        action='invoice.post',
        object_type='Invoice',
        object_id=invoice.pk,
        actor=actor,
        organization=invoice.organization,
        metadata={'total_cents': invoice.total_cents, 'tenant_id': invoice.tenant_id},
        request=request,
    )
    notify_user(
        user=invoice.tenant.user,
        type='INVOICE_POSTED',
        title='Invoice posted',
        body=f'An invoice for {invoice.total_cents} cents is due {invoice.due_date.isoformat()}.',
        organization=invoice.organization,
        payload={'invoice_id': invoice.pk, 'total_cents': invoice.total_cents},
    )
    return invoice


@transaction.atomic
def void_invoice(invoice, *, actor, request=None):
    invoice = Invoice.objects.select_for_update().select_related('organization').get(pk=invoice.pk)
    if invoice.status != DocumentStatus.POSTED:
        raise ValidationError({'status': 'Only a posted invoice can be voided.'})
    if PaymentAllocation.objects.filter(charge__invoice=invoice).exists():
        raise ValidationError({'status': 'Invoices with payment allocations cannot be voided.'})
    invoice.charges.select_for_update().update(
        lifecycle=DocumentStatus.VOIDED,
        balance_cents=0,
        updated_at=timezone.now(),
    )
    invoice.status = DocumentStatus.VOIDED
    invoice.balance_cents = 0
    invoice.save(update_fields=('status', 'balance_cents', 'updated_at'))
    record_audit(
        action='invoice.void',
        object_type='Invoice',
        object_id=invoice.pk,
        actor=actor,
        organization=invoice.organization,
        metadata={'tenant_id': invoice.tenant_id},
        request=request,
    )
    return invoice


@transaction.atomic
def record_payment(
    *,
    tenant,
    amount_cents,
    received_date,
    method,
    actor,
    reference='',
    external_id='',
    request=None,
):
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ValidationError({'amount_cents': 'Amount must be a positive integer number of cents.'})
    if type(received_date).__name__ != 'date':
        raise ValidationError({'received_date': 'Received date must be a civil date.'})
    reference = (reference or '').strip()
    external_id = (external_id or '').strip()
    if external_id:
        existing = Payment.objects.filter(organization=tenant.organization, external_id=external_id).first()
        if existing is not None:
            raise ValidationError({'external_id': 'A payment with this external id already exists.'})
    if reference and Payment.objects.filter(organization=tenant.organization, reference=reference).exists():
        raise ValidationError({'reference': 'A payment with this reference already exists for the organization.'})
    payment = Payment.objects.create(
        organization=tenant.organization,
        tenant=tenant,
        amount_cents=amount_cents,
        received_date=received_date,
        execution_timestamp=timezone.now(),
        method=method,
        status=Payment.Status.PENDING,
        currency='KES',
        reference=reference,
        external_id=external_id,
        recorded_by=actor,
    )
    record_audit(
        action='payment.record',
        object_type='Payment',
        object_id=payment.pk,
        actor=actor,
        organization=payment.organization,
        metadata={'amount_cents': amount_cents, 'tenant_id': tenant.pk},
        request=request,
    )
    return payment


@transaction.atomic
def allocate_payment(payment, *, policy_id, policy_version, actor, request=None):
    payment = (
        Payment.objects.select_for_update(of=('self',))
        .select_related('tenant', 'tenant__user', 'organization')
        .get(pk=payment.pk)
    )
    if payment.status != Payment.Status.PENDING:
        raise ValidationError({'status': 'Only a pending payment can be allocated.'})
    if policy_id != 'CANONICAL_PRIORITY' or policy_version != 2:
        raise ValidationError({'policy_id': 'Allocation is locked to CANONICAL_PRIORITY version 2.'})
    charges = list(
        Charge.objects.select_for_update()
        .filter(
            tenant_id=payment.tenant_id,
            organization_id=payment.organization_id,
            lifecycle=DocumentStatus.POSTED,
            balance_cents__gt=0,
            currency='KES',
        )
        .exclude(charge_type__in=DEPOSIT_CHARGE_TYPES)
        .select_related('invoice')
    )
    items = [
        AllocationCharge(
            charge_id=str(charge.id),
            invoice_id=str(charge.invoice_id),
            tenant_id=str(charge.tenant_id),
            charge_type=charge.charge_type,
            due_date=charge.due_date,
            balance_cents=int(charge.balance_cents),
            period_start=charge.period_start,
            currency='KES',
            lifecycle=charge.lifecycle,
        )
        for charge in charges
    ]
    stamp = _utc_stamp(payment.execution_timestamp)
    try:
        result = allocate(
            payment_cents=int(payment.amount_cents),
            tenant_id=str(payment.tenant_id),
            currency='KES',
            source_id=str(payment.id),
            effective_date=payment.received_date,
            execution_timestamp_utc=stamp,
            items=items,
            policy_id=policy_id,
            policy_version=policy_version,
        )
    except (AllocationError, MoneyError, ValueError) as error:
        raise ValidationError({'detail': str(error)}) from error
    if result.allocated_cents + result.overpayment_cents != payment.amount_cents:
        raise ValidationError({'detail': 'Allocation did not conserve the payment amount.'})
    by_id = {str(charge.id): charge for charge in charges}
    touched_invoices = set()
    for line in result.lines:
        charge = by_id.get(line.item_id)
        if charge is None or charge.tenant_id != payment.tenant_id:
            raise ValidationError({'detail': 'Allocation referenced a charge for a different tenant.'})
        if line.amount_cents > charge.balance_cents:
            raise ValidationError({'detail': 'Allocation exceeded the charge balance.'})
        charge.balance_cents -= line.amount_cents
        charge.save(update_fields=('balance_cents', 'updated_at'))
        PaymentAllocation.objects.create(
            payment=payment,
            charge=charge,
            amount_cents=line.amount_cents,
            policy_id=line.policy_id,
            policy_version=line.policy_version,
        )
        touched_invoices.add(charge.invoice_id)
    for posting in result.postings:
        if posting.account == '2030':
            raise ValidationError({'detail': 'Overpayment must not post to account 2030.'})
        LedgerPosting.objects.create(
            payment=payment,
            account=posting.account,
            direction=posting.direction,
            amount_cents=posting.amount_cents,
        )
    payment.allocated_cents = result.allocated_cents
    payment.overpayment_cents = result.overpayment_cents
    payment.status = Payment.Status.ALLOCATED
    payment.policy_id = result.policy_id
    payment.policy_version = result.policy_version
    payment.save(update_fields=(
        'allocated_cents',
        'overpayment_cents',
        'status',
        'policy_id',
        'policy_version',
        'updated_at',
    ))
    for invoice in Invoice.objects.filter(pk__in=touched_invoices):
        recompute_invoice_totals(invoice)
    record_audit(
        action='payment.allocate',
        object_type='Payment',
        object_id=payment.pk,
        actor=actor,
        organization=payment.organization,
        metadata={
            'allocated_cents': result.allocated_cents,
            'overpayment_cents': result.overpayment_cents,
            'policy_id': result.policy_id,
            'policy_version': result.policy_version,
        },
        request=request,
    )
    notify_user(
        user=payment.tenant.user,
        type='PAYMENT_RECEIVED',
        title='Payment allocated',
        body=f'{result.allocated_cents} cents were applied. Overpayment {result.overpayment_cents} cents.',
        organization=payment.organization,
        payload={
            'payment_id': str(payment.pk),
            'allocated_cents': result.allocated_cents,
            'overpayment_cents': result.overpayment_cents,
        },
    )
    return payment


@transaction.atomic
def reverse_payment(payment, *, reason, actor, request=None):
    """Fully reverse a posted rental payment, retaining all original rows.

    M-Pesa reversal claims are only recorded for authorised review. The local
    integration verifies STK settlement, not provider-side reversal events.
    """
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'A non-empty reversal reason is required.'})

    payment = Payment.objects.select_for_update().select_related(
        'organization', 'tenant', 'tenant__user',
    ).get(pk=payment.pk)
    existing = PaymentReversal.objects.filter(payment=payment).first()
    if existing is not None:
        if existing.reason == reason:
            return existing
        raise ValidationError({'status': 'A reversal request already exists for this payment.'})
    if payment.status == Payment.Status.VOIDED:
        raise ValidationError({'status': 'A voided payment cannot be reversed.'})
    if payment.status == Payment.Status.REVERSED:
        raise ValidationError({'status': 'The payment is already reversed.'})
    if payment.status != Payment.Status.ALLOCATED:
        raise ValidationError({'status': 'Only a posted, allocated payment can be reversed.'})

    allocations = list(
        PaymentAllocation.objects.select_for_update()
        .filter(payment=payment)
        .select_related('charge')
        .order_by('charge_id', 'pk')
    )
    postings = list(LedgerPosting.objects.select_for_update().filter(payment=payment).order_by('pk'))
    allocated_total = sum(row.amount_cents for row in allocations)
    if allocated_total != payment.allocated_cents:
        raise ValidationError({'status': 'Payment allocation history is inconsistent; review is required.'})
    if payment.allocated_cents + payment.overpayment_cents != payment.amount_cents:
        raise ValidationError({'status': 'Payment amount history is inconsistent; review is required.'})
    debits = sum(row.amount_cents for row in postings if row.direction == 'DEBIT')
    credits = sum(row.amount_cents for row in postings if row.direction == 'CREDIT')
    if not postings or debits != credits or debits != payment.amount_cents:
        raise ValidationError({'status': 'Payment ledger history is inconsistent; review is required.'})

    # A provider transaction must not be represented as reversed based only on
    # an operator-entered reference or unverified callback claim.
    if payment.method == Payment.Method.MPESA:
        reversal = PaymentReversal.objects.create(
            payment=payment,
            authorized_by=actor,
            reason=reason,
            amount_cents=payment.amount_cents,
            status=PaymentReversal.Status.REVIEW_REQUIRED,
        )
        record_audit(
            action='payment.reversal_review_required',
            object_type='PaymentReversal',
            object_id=reversal.pk,
            actor=actor,
            organization=payment.organization,
            metadata={
                'payment_id': str(payment.pk),
                'amount_cents': reversal.amount_cents,
                'reason': reason,
                'status': reversal.status,
                'provider_evidence_required': True,
            },
            request=request,
        )
        return reversal

    if any(row.charge.lifecycle != DocumentStatus.POSTED for row in allocations):
        raise ValidationError({'status': 'A payment allocation no longer references a posted charge.'})

    reversal = PaymentReversal.objects.create(
        payment=payment,
        authorized_by=actor,
        reason=reason,
        amount_cents=payment.amount_cents,
        status=PaymentReversal.Status.REVERSED,
    )
    touched_charges = {row.charge_id: row.charge for row in allocations}
    for allocation in allocations:
        PaymentReversalAllocation.objects.create(
            reversal=reversal,
            original_allocation=allocation,
            charge_id=allocation.charge_id,
            amount_cents=allocation.amount_cents,
        )
    for posting in postings:
        LedgerPosting.objects.create(
            payment=payment,
            reversal=reversal,
            account=posting.account,
            direction='CREDIT' if posting.direction == 'DEBIT' else 'DEBIT',
            amount_cents=posting.amount_cents,
        )

    payment.status = Payment.Status.REVERSED
    payment.save(update_fields=('status', 'updated_at'))
    touched_invoice_ids = set()
    for charge in touched_charges.values():
        active_allocations = PaymentAllocation.objects.filter(
            charge=charge,
            payment__status=Payment.Status.ALLOCATED,
        ).aggregate(total=Sum('amount_cents'))['total'] or 0
        if active_allocations > charge.amount_cents:
            raise ValidationError({'status': 'Active allocations exceed the charge amount; review is required.'})
        charge.balance_cents = charge.amount_cents - active_allocations
        charge.save(update_fields=('balance_cents', 'updated_at'))
        touched_invoice_ids.add(charge.invoice_id)
    for invoice in Invoice.objects.filter(pk__in=touched_invoice_ids).order_by('pk'):
        recompute_invoice_totals(invoice)

    record_audit(
        action='payment.reverse',
        object_type='PaymentReversal',
        object_id=reversal.pk,
        actor=actor,
        organization=payment.organization,
        metadata={
            'payment_id': str(payment.pk),
            'amount_cents': reversal.amount_cents,
            'allocated_cents': payment.allocated_cents,
            'unallocated_cents': payment.overpayment_cents,
            'allocation_count': len(allocations),
            'posting_count': len(postings),
            'reason': reason,
            'status': reversal.status,
        },
        request=request,
    )
    if payment.tenant.user_id:
        notify_user(
            user=payment.tenant.user,
            type='PAYMENT_REVERSED',
            title='Payment reversed',
            body=f'A payment of {payment.amount_cents} cents was reversed.',
            organization=payment.organization,
            payload={'payment_id': str(payment.pk), 'reversal_id': str(reversal.pk)},
        )
    return reversal


def assess_tenant_delinquency(*, tenant, as_of, grace_days):
    from engines.delinquency.facade import DelinquencyObligation, assess
    from rental_os.algorithms.delinquency import DelinquencyError

    if type(as_of) is not date:
        raise ValidationError({'as_of': 'as_of must be a civil date.'})
    if isinstance(grace_days, bool) or not isinstance(grace_days, int) or grace_days < 0:
        raise ValidationError({'grace_days': 'grace_days must be an integer >= 0.'})
    charges = Charge.objects.filter(tenant=tenant).order_by('due_date')
    obligations = [
        DelinquencyObligation(
            obligation_id=str(charge.id),
            due_date=charge.due_date,
            balance_cents=int(charge.balance_cents),
            lifecycle=charge.lifecycle,
        )
        for charge in charges
    ]
    try:
        result = assess(obligations=obligations, as_of=as_of, grace_days=grace_days)
    except (DelinquencyError, MoneyError) as error:
        raise ValidationError({'detail': str(error)}) from error
    return {
        'tenant': tenant.pk,
        'as_of': as_of.isoformat(),
        'grace_days': grace_days,
        'status': result.status,
        'open_cents': result.open_cents,
        'current_cents': result.current_cents,
        'grace_cents': result.grace_cents,
        'delinquent_cents': result.delinquent_cents,
        'items': [
            {
                'obligation_id': item.obligation_id,
                'status': item.status,
                'balance_cents': item.balance_cents,
                'days_past_due': item.days_past_due,
            }
            for item in result.items
        ],
    }
