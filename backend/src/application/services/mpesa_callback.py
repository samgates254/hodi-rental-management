"""Settle Safaricom STK callbacks onto canonical HODI Payment rows.

Does not call Daraja. Does not hold a transaction open across HTTP.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.billing.models import MpesaAttempt, Payment
from application.services.audit import record_audit
from application.services.billing import allocate_payment, record_payment
from application.services.mpesa import normalize_kenya_msisdn

logger = logging.getLogger(__name__)

NAIROBI = ZoneInfo('Africa/Nairobi')
POLICY_ID = 'CANONICAL_PRIORITY'
POLICY_VERSION = 2

# Daraja ResultCode values observed on STK callbacks. 0 is success after metadata checks.
CANCELLED_CODES = frozenset({'1031', '1032'})
TIMEOUT_CODES = frozenset({'1019', '1025', '1037'})
OPEN_STATUSES = frozenset({MpesaAttempt.Status.INITIATED, MpesaAttempt.Status.STK_SENT})
TERMINAL_FAILURE = frozenset({
    MpesaAttempt.Status.FAILED,
    MpesaAttempt.Status.CANCELLED,
    MpesaAttempt.Status.TIMEOUT,
})


class CallbackValidationError(Exception):
    """Success-callback metadata failed HODI checks. Do not create a Payment."""


def classify_stk_query(attempt, query) -> tuple[str, str, str]:
    """Return transaction outcome only when the query response is tied to this attempt.

    Daraja ResponseCode acknowledges the query request. ResultCode is the
    queried STK transaction result. Missing fields/references are unresolved.
    """
    if not isinstance(query, dict) or str(query.get('ResponseCode') or '').strip() != '0':
        return 'UNRESOLVED', '', ''
    result_code = str(query.get('ResultCode') or '').strip()
    checkout = str(query.get('CheckoutRequestID') or '').strip()
    merchant = str(query.get('MerchantRequestID') or '').strip()
    if (not result_code or checkout != str(attempt.checkout_request_id or '')
            or merchant != str(attempt.merchant_request_id or '')):
        return 'UNRESOLVED', '', ''
    return ('SUCCESS' if result_code == '0' else 'FAILED', result_code,
            str(query.get('ResultDesc') or ''))


@dataclass
class CallbackResult:
    matched: bool
    settled: bool
    duplicate: bool
    status: str
    detail: str
    attempt: MpesaAttempt | None = None
    payment: Payment | None = None


def parse_stk_callback(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError({'detail': 'Callback body must be a JSON object.'})
    body = payload.get('Body', payload.get('body'))
    if not isinstance(body, dict):
        raise ValidationError({'detail': 'Callback Body is required.'})
    stk = body.get('stkCallback')
    if not isinstance(stk, dict):
        raise ValidationError({'detail': 'Callback stkCallback is required.'})
    checkout = str(stk.get('CheckoutRequestID') or '').strip()
    if not checkout:
        raise ValidationError({'detail': 'CheckoutRequestID is required.'})
    if stk.get('ResultCode') is None or stk.get('ResultCode') == '':
        raise ValidationError({'detail': 'ResultCode is required.'})
    return stk


def _result_code(stk) -> str:
    return str(stk.get('ResultCode')).strip()


def map_failure_status(result_code: str) -> str:
    if result_code in CANCELLED_CODES:
        return MpesaAttempt.Status.CANCELLED
    if result_code in TIMEOUT_CODES:
        return MpesaAttempt.Status.TIMEOUT
    return MpesaAttempt.Status.FAILED


def _metadata_map(stk) -> dict:
    meta = stk.get('CallbackMetadata') or {}
    if not isinstance(meta, dict):
        return {}
    items = meta.get('Item') or []
    parsed = {}
    if not isinstance(items, list):
        return parsed
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get('Name')
        if name:
            parsed[str(name)] = item.get('Value')
    return parsed


def _amount_to_cents(value) -> int:
    if isinstance(value, bool) or value is None:
        raise CallbackValidationError('Callback Amount is required.')
    try:
        shillings = Decimal(str(value))
    except InvalidOperation as error:
        raise CallbackValidationError('Callback Amount is invalid.') from error
    if shillings != shillings.to_integral_value():
        raise CallbackValidationError('Callback Amount must be whole Kenyan shillings.')
    cents = int(shillings) * 100
    if cents <= 0:
        raise CallbackValidationError('Callback Amount must be positive.')
    return cents


def _parse_transaction_date(value):
    if value is None or value == '':
        return timezone.localdate()
    raw = str(value).strip()
    try:
        moment = datetime.strptime(raw, '%Y%m%d%H%M%S').replace(tzinfo=NAIROBI)
    except ValueError as error:
        raise CallbackValidationError('Callback TransactionDate is invalid.') from error
    return moment.date()


def _phones_match(attempt_phone: str, callback_phone) -> bool:
    if callback_phone is None or str(callback_phone).strip() == '':
        return True
    try:
        normalized = normalize_kenya_msisdn(str(callback_phone))
    except ValidationError:
        return False
    return normalized == attempt_phone


def _ack(*, matched, settled, duplicate, status, detail, attempt=None, payment=None):
    return CallbackResult(
        matched=matched,
        settled=settled,
        duplicate=duplicate,
        status=status,
        detail=detail,
        attempt=attempt,
        payment=payment,
    )


def _lock_attempt(checkout_request_id: str) -> MpesaAttempt | None:
    return (
        MpesaAttempt.objects
        .select_for_update(of=('self',))
        .select_related('tenant', 'organization', 'initiated_by')
        .filter(checkout_request_id=checkout_request_id)
        .first()
    )


def _existing_payment(*, organization, receipt: str) -> Payment | None:
    return Payment.objects.filter(organization=organization, external_id=receipt).first()


def _mark_attempt(attempt, *, status, result_code, result_description, receipt=None):
    attempt.status = status
    attempt.result_code = result_code
    attempt.result_description = result_description or ''
    update = ('status', 'result_code', 'result_description', 'updated_at')
    if receipt:
        attempt.mpesa_receipt_number = receipt
        update = update + ('mpesa_receipt_number',)
    attempt.save(update_fields=update)
    return attempt


def _create_or_load_payment(*, attempt, receipt, received_date, request):
    existing = _existing_payment(organization=attempt.organization, receipt=receipt)
    if existing is not None:
        return existing, False
    try:
        payment = record_payment(
            tenant=attempt.tenant,
            amount_cents=int(attempt.amount_cents),
            received_date=received_date,
            method=Payment.Method.MPESA,
            actor=attempt.initiated_by,
            reference=receipt,
            external_id=receipt,
            request=request,
        )
        return payment, True
    except ValidationError as error:
        raced = _existing_payment(organization=attempt.organization, receipt=receipt)
        if raced is not None:
            return raced, False
        raise error
    except IntegrityError:
        raced = _existing_payment(organization=attempt.organization, receipt=receipt)
        if raced is not None:
            return raced, False
        raise


def _allocate_if_pending(payment, *, actor, request):
    if payment.status == Payment.Status.ALLOCATED:
        return payment
    if payment.status != Payment.Status.PENDING:
        raise CallbackValidationError('Existing payment cannot be allocated.')
    try:
        return allocate_payment(
            payment,
            policy_id=POLICY_ID,
            policy_version=POLICY_VERSION,
            actor=actor,
            request=request,
        )
    except ValidationError as error:
        payment.refresh_from_db()
        if payment.status == Payment.Status.ALLOCATED:
            return payment
        raise error


def _validate_success(attempt, stk) -> tuple[str, object]:
    if attempt.currency != 'KES':
        raise CallbackValidationError('Attempt currency must be KES.')
    if attempt.tenant_id is None or attempt.organization_id is None:
        raise CallbackValidationError('Attempt is missing tenant or organization.')
    merchant = str(stk.get('MerchantRequestID') or '').strip()
    if not attempt.merchant_request_id or not merchant or merchant != attempt.merchant_request_id:
        raise CallbackValidationError('MerchantRequestID does not match the attempt.')
    meta = _metadata_map(stk)
    receipt = str(meta.get('MpesaReceiptNumber') or '').strip()
    if not receipt:
        raise CallbackValidationError('MpesaReceiptNumber is required for a successful payment.')
    amount_cents = _amount_to_cents(meta.get('Amount'))
    if amount_cents != int(attempt.amount_cents):
        raise CallbackValidationError('Callback Amount does not match the attempt.')
    if not _phones_match(attempt.phone_number, meta.get('PhoneNumber')):
        raise CallbackValidationError('Callback PhoneNumber does not match the attempt.')
    received_date = _parse_transaction_date(meta.get('TransactionDate'))
    return receipt, received_date


def validate_stk_success_callback(attempt, payload):
    """Validate success metadata without mutating attempts or ledger records."""
    stk = parse_stk_callback(payload)
    if _result_code(stk) != '0':
        raise CallbackValidationError('Callback is not a successful STK result.')
    return _validate_success(attempt, stk)


@transaction.atomic
def settle_verified_stk_failure(*, checkout_request_id, merchant_request_id, result_code, result_description='', provider_query, request=None):
    """Apply a provider-verified terminal failure while holding the attempt lock."""
    attempt = _lock_attempt(checkout_request_id)
    if attempt is None or not attempt.merchant_request_id or attempt.merchant_request_id != merchant_request_id:
        return _ack(matched=False, settled=False, duplicate=False, status='UNRESOLVED',
                    detail='Provider result could not be matched to the stored attempt.')
    outcome, verified_code, verified_description = classify_stk_query(attempt, provider_query)
    if outcome != 'FAILED' or verified_code != str(result_code):
        return _ack(matched=True, settled=False, duplicate=False, status='UNRESOLVED',
                    detail='Provider outcome is not a verified failure.', attempt=attempt)
    if attempt.status == MpesaAttempt.Status.SUCCESS:
        return _ack(matched=True, settled=True, duplicate=True, status=attempt.status,
                    detail='Attempt was already settled.', attempt=attempt)
    if attempt.status in TERMINAL_FAILURE:
        return _ack(matched=True, settled=False, duplicate=True, status=attempt.status,
                    detail='Attempt was already closed.', attempt=attempt)
    if str(result_code) == '0':
        return _ack(matched=True, settled=False, duplicate=False, status='UNRESOLVED',
                    detail='Provider outcome is not a failure.', attempt=attempt)
    status_value = map_failure_status(str(result_code))
    _mark_attempt(
        attempt,
        status=status_value,
        result_code=str(result_code),
        result_description=verified_description or result_description or 'M-Pesa did not complete the payment.',
    )
    record_audit(
        action='mpesa.stk.provider_failure', object_type='MpesaAttempt', object_id=attempt.pk,
        actor=attempt.initiated_by, organization=attempt.organization,
        metadata={'result_code': str(result_code), 'status': status_value}, request=request,
    )
    return _ack(matched=True, settled=False, duplicate=False, status=attempt.status,
                detail='Provider confirmed that M-Pesa did not complete the payment.', attempt=attempt)


def settle_stk_callback(*, payload, provider_query=None, request=None) -> CallbackResult:
    stk = parse_stk_callback(payload)
    checkout = str(stk.get('CheckoutRequestID')).strip()
    result_code = _result_code(stk)
    result_desc = str(stk.get('ResultDesc') or '')

    with transaction.atomic():
        attempt = _lock_attempt(checkout)
        if attempt is None:
            logger.warning('Daraja STK callback did not match a stored checkout request')
            record_audit(
                action='mpesa.stk.unmatched',
                object_type='MpesaAttempt',
                object_id=checkout,
                request=request,
                metadata={'result_code': result_code},
            )
            return _ack(
                matched=False, settled=False, duplicate=False, status='UNMATCHED',
                detail='Callback is unmatched and requires reconciliation.',
            )

        if _result_code(stk) != '0':
            return _ack(matched=True, settled=False, duplicate=False, status='UNRESOLVED',
                        detail='Only a provider-verified success can be settled as a payment.', attempt=attempt)
        query_outcome, query_code, _query_description = classify_stk_query(attempt, provider_query)
        if query_outcome != 'SUCCESS' or query_code != '0':
            return _ack(matched=True, settled=False, duplicate=False, status='UNRESOLVED',
                        detail='Provider outcome is not a verified success.', attempt=attempt)

        if attempt.status == MpesaAttempt.Status.SUCCESS:
            payment = None
            if attempt.mpesa_receipt_number:
                payment = _existing_payment(
                    organization=attempt.organization,
                    receipt=attempt.mpesa_receipt_number,
                )
            return _ack(
                matched=True,
                settled=True,
                duplicate=True,
                status=attempt.status,
                detail='Payment already settled.',
                attempt=attempt,
                payment=payment,
            )

        if result_code != '0':
            return _ack(matched=True, settled=False, duplicate=False, status='UNRESOLVED',
                        detail='A provider-verified failure result is required before closing this attempt.',
                        attempt=attempt)

        if attempt.status in TERMINAL_FAILURE:
            return _ack(
                matched=True,
                settled=False,
                duplicate=True,
                status=attempt.status,
                detail='Attempt is already closed. No payment was recorded.',
                attempt=attempt,
            )

        try:
            receipt, received_date = _validate_success(attempt, stk)
        except CallbackValidationError as error:
            record_audit(
                action='mpesa.stk.callback_discrepancy',
                object_type='MpesaAttempt',
                object_id=attempt.pk,
                actor=attempt.initiated_by,
                organization=attempt.organization,
                metadata={'result_code': result_code},
                request=request,
            )
            return _ack(
                matched=True,
                settled=False,
                duplicate=False,
                status='UNRESOLVED',
                detail='Callback failed validation. No payment was recorded and the attempt remains open.',
                attempt=attempt,
            )

        other = (
            MpesaAttempt.objects
            .filter(mpesa_receipt_number=receipt)
            .exclude(pk=attempt.pk)
            .first()
        )
        if other is not None:
            _mark_attempt(
                attempt,
                status=MpesaAttempt.Status.FAILED,
                result_code=result_code,
                result_description='Duplicate M-Pesa receipt number.',
            )
            return _ack(
                matched=True,
                settled=False,
                duplicate=True,
                status=attempt.status,
                detail='Duplicate M-Pesa receipt. No additional payment was recorded.',
                attempt=attempt,
            )

        payment, _created = _create_or_load_payment(
            attempt=attempt,
            receipt=receipt,
            received_date=received_date,
            request=request,
        )
        if payment.tenant_id != attempt.tenant_id or payment.organization_id != attempt.organization_id:
            _mark_attempt(
                attempt,
                status=MpesaAttempt.Status.FAILED,
                result_code=result_code,
                result_description='Receipt is already tied to another tenant or organization.',
            )
            return _ack(
                matched=True,
                settled=False,
                duplicate=True,
                status=attempt.status,
                detail='Receipt belongs to another payment. No additional payment was recorded.',
                attempt=attempt,
            )
        payment = _allocate_if_pending(
            payment,
            actor=attempt.initiated_by,
            request=request,
        )
        try:
            with transaction.atomic():
                _mark_attempt(
                    attempt,
                    status=MpesaAttempt.Status.SUCCESS,
                    result_code=result_code,
                    result_description=result_desc or 'The service request is processed successfully.',
                    receipt=receipt,
                )
        except IntegrityError:
            attempt.refresh_from_db()
            return _ack(
                matched=True,
                settled=attempt.status == MpesaAttempt.Status.SUCCESS,
                duplicate=True,
                status=attempt.status,
                detail='Duplicate M-Pesa receipt. No additional payment was recorded.',
                attempt=attempt,
                payment=payment,
            )
        record_audit(
            action='mpesa.stk.settle',
            object_type='MpesaAttempt',
            object_id=attempt.pk,
            actor=attempt.initiated_by,
            organization=attempt.organization,
            metadata={
                'payment_id': str(payment.pk),
                'amount_cents': attempt.amount_cents,
            },
            request=request,
        )
        return _ack(
            matched=True,
            settled=True,
            duplicate=False,
            status=attempt.status,
            detail='Payment settled.',
            attempt=attempt,
            payment=payment,
        )
