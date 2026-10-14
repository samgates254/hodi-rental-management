"""Settle Safaricom STK callbacks onto canonical HODI Payment rows.

Does not call Daraja. Does not hold a transaction open across HTTP.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.billing.models import MpesaAttempt, Payment
from application.services.audit import record_audit
from application.services.billing import allocate_payment, record_payment
from application.services.mpesa import normalize_kenya_msisdn
from common.rental_dates import RENTAL_BUSINESS_TIME_ZONE as NAIROBI, rental_business_date

logger = logging.getLogger(__name__)

# Daraja's callback date has civil-date precision, not a timezone-aware
# timestamp. Accept the checkout day and the following Nairobi date to cover
# midnight crossing; callback delivery itself may be delayed. Older or later
# transaction dates require operator/provider reconciliation.
MAX_STK_TRANSACTION_DATE_DELAY_DAYS = 1
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


class TransactionDateValidationError(CallbackValidationError):
    """Provider date is implausible for the stored checkout attempt."""


class DuplicateReceiptConflict(Exception):
    """A globally unique Safaricom receipt was concurrently assigned elsewhere."""


def classify_stk_query(attempt, query, *, conservative=False) -> tuple[str, str, str]:
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
    # Daraja's ResponseCode acknowledges the query request, not the underlying
    # transaction. Treat success as verified only with a complete result.
    # Automatic reconciliation is deliberately conservative: only known
    # terminal cancellation/timeout codes may close an attempt. The callback
    # path can still validate a specific nonzero result against its matching
    # provider query without misclassifying an unknown code as a known state.
    description = query.get('ResultDesc')
    if not isinstance(description, str) or not description.strip():
        return 'UNRESOLVED', '', ''
    if result_code == '0':
        return 'SUCCESS', result_code, description.strip()
    if not conservative or result_code in CANCELLED_CODES | TIMEOUT_CODES:
        return 'FAILED', result_code, description.strip()
    return 'UNRESOLVED', '', ''


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
        raise CallbackValidationError('Callback TransactionDate is required.')
    raw = str(value).strip()
    try:
        moment = datetime.strptime(raw, '%Y%m%d%H%M%S').replace(tzinfo=NAIROBI)
    except ValueError as error:
        raise CallbackValidationError('Callback TransactionDate is invalid.') from error
    return moment.date()


def validate_stk_transaction_date(attempt, transaction_date):
    """Apply the shared callback and operator-review civil-date policy.

    Daraja sends only a Nairobi civil transaction date. It must be on the
    checkout's Nairobi creation date or the following civil date, and not later
    than today's Nairobi date. This permits midnight crossing and delayed
    callback delivery while routing an unrelated transaction date to review.
    """
    attempt_date = rental_business_date(attempt.created_at)
    today = rental_business_date()
    latest_transaction_date = attempt_date + timedelta(days=MAX_STK_TRANSACTION_DATE_DELAY_DAYS)
    if transaction_date < attempt_date or transaction_date > min(today, latest_transaction_date):
        raise TransactionDateValidationError(
            'Callback TransactionDate is outside the stored attempt date range.'
        )
    return transaction_date


def _phones_match(attempt_phone: str, callback_phone) -> bool:
    if callback_phone is None or str(callback_phone).strip() == '':
        return False
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


def _payment_matches_attempt(payment, *, attempt, receipt, received_date) -> bool:
    return (
        payment.organization_id == attempt.organization_id
        and payment.tenant_id == attempt.tenant_id
        and payment.method == Payment.Method.MPESA
        and payment.currency == attempt.currency
        and payment.amount_cents == int(attempt.amount_cents)
        and payment.external_id == receipt
        and payment.received_date == received_date
        and payment.status in {Payment.Status.PENDING, Payment.Status.ALLOCATED}
    )


def _mark_attempt_unresolved(attempt, *, reason, request):
    attempt.reconciliation_state = MpesaAttempt.ReconciliationState.UNRESOLVED
    attempt.save(update_fields=('reconciliation_state', 'updated_at'))
    record_audit(
        action='mpesa.stk.callback_discrepancy',
        object_type='MpesaAttempt',
        object_id=attempt.pk,
        actor=attempt.initiated_by,
        organization=attempt.organization,
        metadata={'reason': reason},
        request=request,
    )


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
    received_date = validate_stk_transaction_date(
        attempt,
        _parse_transaction_date(meta.get('TransactionDate')),
    )
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
    """Settle a verified callback, rolling back all writes on receipt races."""
    stk = parse_stk_callback(payload)
    checkout = str(stk.get('CheckoutRequestID')).strip()
    try:
        return _settle_stk_callback_transaction(
            payload=payload,
            provider_query=provider_query,
            request=request,
        )
    except DuplicateReceiptConflict:
        # The transaction which created/allocated a losing payment must be
        # rolled back before we record the unresolved reconciliation outcome.
        with transaction.atomic():
            attempt = _lock_attempt(checkout)
            if attempt is None:
                return _ack(
                    matched=False,
                    settled=False,
                    duplicate=True,
                    status='UNRESOLVED',
                    detail='Receipt conflict requires reconciliation.',
                )
            if attempt.status == MpesaAttempt.Status.SUCCESS:
                payment = _existing_payment(
                    organization=attempt.organization,
                    receipt=attempt.mpesa_receipt_number or '',
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
            _mark_attempt_unresolved(
                attempt,
                reason='duplicate_receipt_race',
                request=request,
            )
            return _ack(
                matched=True,
                settled=False,
                duplicate=True,
                status='UNRESOLVED',
                detail='Receipt was assigned to another attempt. No payment was recorded for this attempt.',
                attempt=attempt,
            )


def _settle_stk_callback_transaction(*, payload, provider_query=None, request=None) -> CallbackResult:
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
            try:
                callback_receipt, _received_date = _validate_success(attempt, stk)
            except CallbackValidationError:
                record_audit(
                    action='mpesa.stk.callback_discrepancy', object_type='MpesaAttempt',
                    object_id=attempt.pk, actor=attempt.initiated_by, organization=attempt.organization,
                    metadata={'reason': 'duplicate_callback_metadata_invalid'}, request=request,
                )
                return _ack(
                    matched=True, settled=False, duplicate=False, status='UNRESOLVED',
                    detail='Callback conflicts with the settled attempt; no payment state changed.',
                    attempt=attempt,
                )
            if callback_receipt != attempt.mpesa_receipt_number:
                record_audit(
                    action='mpesa.stk.callback_discrepancy', object_type='MpesaAttempt',
                    object_id=attempt.pk, actor=attempt.initiated_by, organization=attempt.organization,
                    metadata={'reason': 'duplicate_callback_receipt_conflict'}, request=request,
                )
                return _ack(
                    matched=True, settled=False, duplicate=False, status='UNRESOLVED',
                    detail='Callback receipt conflicts with the settled attempt; no payment state changed.',
                    attempt=attempt,
                )
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
        except TransactionDateValidationError:
            _mark_attempt_unresolved(
                attempt,
                reason='transaction_date_outside_attempt_range',
                request=request,
            )
            return _ack(
                matched=True,
                settled=False,
                duplicate=False,
                status='UNRESOLVED',
                detail='Callback transaction date requires reconciliation. No payment was recorded.',
                attempt=attempt,
            )
        except CallbackValidationError:
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

        receipt_payments = list(Payment.objects.filter(external_id=receipt).order_by('created_at', 'pk')[:2])
        if receipt_payments:
            if (
                len(receipt_payments) != 1
                or not _payment_matches_attempt(
                    receipt_payments[0],
                    attempt=attempt,
                    receipt=receipt,
                    received_date=received_date,
                )
            ):
                _mark_attempt_unresolved(
                    attempt,
                    reason='existing_payment_receipt_conflict',
                    request=request,
                )
                return _ack(
                    matched=True,
                    settled=False,
                    duplicate=True,
                    status='UNRESOLVED',
                    detail='Receipt is already attached to a different payment. No payment state changed.',
                    attempt=attempt,
                )

        payment, _created = _create_or_load_payment(
            attempt=attempt,
            receipt=receipt,
            received_date=received_date,
            request=request,
        )
        if not _payment_matches_attempt(
            payment,
            attempt=attempt,
            receipt=receipt,
            received_date=received_date,
        ):
            _mark_attempt_unresolved(
                attempt,
                reason='existing_payment_receipt_conflict',
                request=request,
            )
            return _ack(
                matched=True,
                settled=False,
                duplicate=True,
                status='UNRESOLVED',
                detail='Receipt is already attached to a different payment. No payment state changed.',
                attempt=attempt,
            )
        payment = _allocate_if_pending(
            payment,
            actor=attempt.initiated_by,
            request=request,
        )
        try:
            _mark_attempt(
                attempt,
                status=MpesaAttempt.Status.SUCCESS,
                result_code=result_code,
                result_description=result_desc or 'The service request is processed successfully.',
                receipt=receipt,
            )
        except IntegrityError as error:
            # Let the exception escape the outer transaction so the payment,
            # allocations, invoice balances, and ledger postings all roll back.
            raise DuplicateReceiptConflict from error
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
