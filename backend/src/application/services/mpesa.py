"""HODI application service for M-Pesa STK initiation.

Creates MpesaAttempt rows and talks to Daraja through MpesaClient.
Does not create Payment, PaymentAllocation, or LedgerPosting rows.
"""

from __future__ import annotations

import logging
import re
import hashlib
import json

from django.db import IntegrityError, transaction
from django.db.models import Sum

from rest_framework.exceptions import APIException, NotFound, ValidationError

from apps.billing.models import (
    DEPOSIT_CHARGE_TYPES,
    Charge,
    DocumentStatus,
    Invoice,
    MpesaAttempt,
)
from apps.billing.statements import tenant_for_statement
from apps.tenants.models import Tenant
from application.services.audit import record_audit
from infrastructure.payments.mpesa import (
    MpesaAuthError,
    MpesaClient,
    MpesaConfigError,
    MpesaError,
    MpesaHTTPError,
    MpesaResponseError,
    MpesaTimeoutError,
)
from rental_os.algorithms.money import MoneyError, require_cents

logger = logging.getLogger(__name__)

KENYA_MSISDN = re.compile(r'^254[17]\d{8}$')


class MpesaUnavailable(APIException):
    status_code = 503
    default_detail = 'M-Pesa is temporarily unavailable.'
    default_code = 'mpesa_unavailable'


def normalize_kenya_msisdn(raw) -> str:
    if raw is None or str(raw).strip() == '':
        raise ValidationError({'phone_number': 'Phone number is required.'})
    digits = re.sub(r'\D', '', str(raw))
    if digits.startswith('0') and len(digits) == 10:
        digits = '254' + digits[1:]
    elif len(digits) == 9 and digits[0] in '17':
        digits = '254' + digits
    if not KENYA_MSISDN.match(digits):
        raise ValidationError({
            'phone_number': 'Enter a Kenyan mobile number that can receive an M-Pesa STK prompt.',
        })
    return digits


def kes_from_cents(amount_cents: int) -> int:
    try:
        cents = require_cents(amount_cents, name='amount_cents', allow_zero=False)
    except MoneyError as error:
        raise ValidationError({
            'amount_cents': 'Amount must be a positive integer number of cents.',
        }) from error
    if cents % 100 != 0:
        raise ValidationError({
            'amount_cents': 'Amount must be a whole number of Kenyan shillings (cents divisible by 100).',
        })
    return cents // 100


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _account_reference(*, tenant, invoice) -> str:
    if invoice is not None:
        return str(invoice.pk)[:12]
    return f'T{tenant.pk}'[:12]


def _load_invoice(*, invoice_id, tenant):
    if invoice_id is None:
        return None
    invoice = Invoice.objects.filter(
        pk=invoice_id,
        tenant_id=tenant.pk,
        organization_id=tenant.organization_id,
    ).first()
    if invoice is None:
        raise NotFound('Invoice not found.')
    if invoice.status != DocumentStatus.POSTED:
        raise ValidationError({
            'invoice': 'Payments can only be initiated against a posted invoice.',
        })
    return invoice


def _available_stk_balance(*, tenant):
    """Return rent-ledger due not already reserved by an open STK attempt.

    Allocation is tenant-wide under CANONICAL_PRIORITY v2, so a selected
    invoice is descriptive and does not change which posted charge settles
    first. Deposit charges are excluded because the rent ledger cannot post
    their liability treatment.
    """
    outstanding = sum(
        int(value)
        for value in Charge.objects.select_for_update()
        .filter(
            tenant_id=tenant.pk,
            organization_id=tenant.organization_id,
            lifecycle=DocumentStatus.POSTED,
            balance_cents__gt=0,
            currency='KES',
        )
        .exclude(charge_type__in=DEPOSIT_CHARGE_TYPES)
        .order_by('due_date', 'created_at', 'pk')
        .values_list('balance_cents', flat=True)
    )
    reserved = MpesaAttempt.objects.filter(
        tenant_id=tenant.pk,
        organization_id=tenant.organization_id,
        currency='KES',
        status__in=(MpesaAttempt.Status.INITIATED, MpesaAttempt.Status.STK_SENT),
    ).aggregate(total=Sum('amount_cents'))['total'] or 0
    return max(0, outstanding - int(reserved))


def _mark_failed(attempt, description: str) -> MpesaAttempt:
    attempt.status = MpesaAttempt.Status.FAILED
    attempt.result_description = description
    attempt.save(update_fields=('status', 'result_description', 'updated_at'))
    return attempt


def initiate_mpesa_stk(
    *,
    actor,
    amount_cents,
    phone_number='',
    invoice_id=None,
    idempotency_key=None,
    request=None,
    client=None,
):
    tenant = tenant_for_statement(actor)
    if tenant is None:
        raise NotFound('No active tenant record is linked to this account.')
    if tenant.organization_id is None or not tenant.organization.is_active:
        raise NotFound('No active tenant record is linked to this account.')

    amount_kes = kes_from_cents(amount_cents)
    cents = amount_kes * 100
    phone = normalize_kenya_msisdn(phone_number or tenant.phone_number)
    client = client or MpesaClient.from_settings()
    try:
        client.require_configured()
    except MpesaConfigError as error:
        raise ValidationError({'detail': str(error)}) from error
    try:
        with transaction.atomic():
            # This stable per-tenant row lock serializes independent requests
            # while their pending attempts reserve the same billing balance.
            tenant = Tenant.objects.select_for_update(of=('self',)).select_related(
                'organization',
            ).get(pk=tenant.pk)
            if tenant.organization_id is None or not tenant.organization.is_active:
                raise NotFound('No active tenant record is linked to this account.')
            invoice = _load_invoice(invoice_id=invoice_id, tenant=tenant)
            account_reference = _account_reference(tenant=tenant, invoice=invoice)
            fingerprint = hashlib.sha256(json.dumps({
                'tenant': tenant.pk,
                'invoice': invoice.pk if invoice is not None else None,
                'amount_cents': cents,
                'phone_number': phone,
            }, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()

            if idempotency_key:
                existing = MpesaAttempt.objects.filter(
                    tenant=tenant,
                    idempotency_key=idempotency_key,
                ).first()
                if existing is not None:
                    if existing.request_fingerprint != fingerprint:
                        raise ValidationError({
                            'idempotency_key': 'This key was already used for a different payment request.',
                        })
                    return existing

            available_cents = _available_stk_balance(tenant=tenant)
            if available_cents <= 0:
                raise ValidationError({
                    'amount_cents': 'There is no outstanding rent-ledger balance available for an M-Pesa payment.',
                })
            if cents > available_cents:
                raise ValidationError({
                    'amount_cents': (
                        'Amount exceeds the outstanding balance available after pending M-Pesa requests.'
                    ),
                })

            attempt = MpesaAttempt.objects.create(
                organization=tenant.organization,
                tenant=tenant,
                invoice=invoice,
                initiated_by=actor,
                amount_cents=cents,
                currency='KES',
                phone_number=phone,
                status=MpesaAttempt.Status.INITIATED,
                account_reference=account_reference,
                idempotency_key=idempotency_key or '',
                request_fingerprint=fingerprint if idempotency_key else '',
            )
    except IntegrityError:
        if not idempotency_key:
            raise
        existing = MpesaAttempt.objects.filter(tenant=tenant, idempotency_key=idempotency_key).first()
        if existing is None or existing.request_fingerprint != fingerprint:
            raise ValidationError({'idempotency_key': 'This payment request could not be safely deduplicated.'})
        return existing
    record_audit(
        action='mpesa.stk.initiate',
        object_type='MpesaAttempt',
        object_id=attempt.pk,
        actor=actor,
        organization=attempt.organization,
        metadata={
            'amount_cents': cents,
            'tenant_id': tenant.pk,
            'invoice_id': invoice.pk if invoice is not None else None,
        },
        request=request,
    )

    try:
        result = client.stk_push(
            phone_number=phone,
            amount_kes=amount_kes,
            account_reference=account_reference,
            transaction_desc='Rent payment',
        )
    except MpesaTimeoutError as error:
        attempt.reconciliation_state = MpesaAttempt.ReconciliationState.UNRESOLVED
        attempt.result_description = 'Daraja response timed out; payment prompt outcome is unknown.'
        attempt.save(update_fields=('reconciliation_state', 'result_description', 'updated_at'))
        record_audit(
            action='mpesa.stk.initiate_unresolved', object_type='MpesaAttempt', object_id=attempt.pk,
            actor=actor, organization=attempt.organization,
            metadata={'reason': 'provider_timeout', 'amount_cents': cents}, request=request,
        )
        return attempt
    except MpesaAuthError as error:
        _mark_failed(attempt, 'Daraja rejected the OAuth credentials.')
        raise MpesaUnavailable() from error
    except (MpesaHTTPError, MpesaResponseError, MpesaError) as error:
        attempt.reconciliation_state = MpesaAttempt.ReconciliationState.UNRESOLVED
        attempt.result_description = 'Daraja response was inconclusive; payment prompt outcome is unknown.'
        attempt.save(update_fields=('reconciliation_state', 'result_description', 'updated_at'))
        logger.error('Daraja STK failed attempt_id=%s', attempt.pk)
        return attempt

    attempt.merchant_request_id = _blank_to_none(result.merchant_request_id)
    attempt.checkout_request_id = _blank_to_none(result.checkout_request_id)
    attempt.response_code = _blank_to_none(result.response_code)
    attempt.response_description = result.response_description or ''
    attempt.customer_message = result.customer_message or ''
    if result.accepted:
        if attempt.checkout_request_id and attempt.merchant_request_id:
            attempt.status = MpesaAttempt.Status.STK_SENT
        else:
            attempt.reconciliation_state = MpesaAttempt.ReconciliationState.UNRESOLVED
            attempt.result_description = 'Daraja accepted the request without usable request identifiers.'
    else:
        attempt.status = MpesaAttempt.Status.FAILED
        attempt.result_description = result.response_description or 'Daraja did not accept the STK request.'
    attempt.save(update_fields=(
        'merchant_request_id',
        'checkout_request_id',
        'response_code',
        'response_description',
        'customer_message',
        'status',
        'result_description',
        'reconciliation_state',
        'updated_at',
    ))
    return attempt
