"""HODI application service for M-Pesa STK initiation.

Creates MpesaAttempt rows and talks to Daraja through MpesaClient.
Does not create Payment, PaymentAllocation, or LedgerPosting rows.
"""

from __future__ import annotations

import logging
import re

from rest_framework.exceptions import APIException, NotFound, ValidationError

from apps.billing.models import DocumentStatus, Invoice, MpesaAttempt
from apps.billing.statements import tenant_for_statement
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
    invoice = _load_invoice(invoice_id=invoice_id, tenant=tenant)
    account_reference = _account_reference(tenant=tenant, invoice=invoice)

    client = client or MpesaClient.from_settings()
    try:
        client.require_configured()
    except MpesaConfigError as error:
        raise ValidationError({'detail': str(error)}) from error

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
    )
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
        _mark_failed(attempt, 'Daraja request timed out.')
        raise MpesaUnavailable() from error
    except MpesaAuthError as error:
        _mark_failed(attempt, 'Daraja rejected the OAuth credentials.')
        raise MpesaUnavailable() from error
    except (MpesaHTTPError, MpesaResponseError, MpesaError) as error:
        _mark_failed(attempt, 'Daraja request failed.')
        logger.error('Daraja STK failed attempt_id=%s', attempt.pk)
        raise MpesaUnavailable() from error

    attempt.merchant_request_id = _blank_to_none(result.merchant_request_id)
    attempt.checkout_request_id = _blank_to_none(result.checkout_request_id)
    attempt.response_code = _blank_to_none(result.response_code)
    attempt.response_description = result.response_description or ''
    attempt.customer_message = result.customer_message or ''
    if result.accepted:
        attempt.status = MpesaAttempt.Status.STK_SENT
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
        'updated_at',
    ))
    return attempt
