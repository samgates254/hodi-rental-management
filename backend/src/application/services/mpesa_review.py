"""Authorized operator resolution for STK successes missing callback receipts."""

from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.audit.models import AuditLog
from apps.billing.models import MpesaAttempt, Payment
from application.services.audit import record_audit
from application.services.billing import allocate_payment, record_payment
from application.services.mpesa_callback import TransactionDateValidationError, validate_stk_transaction_date
from application.services.mpesa import normalize_kenya_msisdn
from common.permissions import user_can_access_organization_resource


@transaction.atomic
def resolve_mpesa_attempt_from_evidence(*, attempt_id, actor, evidence, request=None):
    """Settle only a query-confirmed success after staff match external evidence.

    The endpoint captures the operator's attestation and validates every
    provider transaction value against the stored checkout attempt. It cannot
    independently query Safaricom or prove that a supplied statement exists.
    """
    attempt = MpesaAttempt.objects.select_for_update().select_related(
        'organization', 'tenant', 'initiated_by',
    ).filter(pk=attempt_id).first()
    if attempt is None:
        raise NotFound('M-Pesa attempt not found.')
    if not user_can_access_organization_resource(actor, attempt.organization_id, 'billing', 'write'):
        raise NotFound('M-Pesa attempt not found.')
    if actor.pk in (attempt.initiated_by_id, attempt.tenant.user_id):
        raise PermissionDenied('The customer who initiated this attempt cannot review its settlement.')

    try:
        phone = normalize_kenya_msisdn(evidence['phone_number'])
    except (KeyError, ValidationError) as error:
        raise ValidationError({'phone_number': 'A valid provider-confirmed phone number is required.'}) from error

    normalized_evidence = {
        'evidence_source': evidence['evidence_source'],
        'evidence_reference': evidence['evidence_reference'].strip(),
        'amount_cents': evidence['amount_cents'],
        'merchant_request_id': evidence['merchant_request_id'].strip(),
        'checkout_request_id': evidence['checkout_request_id'].strip(),
        'account_reference': evidence['account_reference'].strip(),
        'phone_suffix': phone[-4:],
        'transaction_date': evidence['transaction_date'].isoformat(),
    }
    receipt = evidence['receipt'].strip()

    if attempt.status == MpesaAttempt.Status.SUCCESS:
        audit = AuditLog.objects.filter(
            action='mpesa.stk.operator_settlement', object_type='MpesaAttempt', object_id=str(attempt.pk),
        ).order_by('-created_at', '-pk').first()
        payment = Payment.objects.filter(
            organization_id=attempt.organization_id, external_id=attempt.mpesa_receipt_number,
        ).first()
        if audit and audit.metadata == normalized_evidence and attempt.mpesa_receipt_number == receipt and payment:
            return payment, True
        raise ValidationError({'attempt': 'This attempt is already settled with different evidence.'})

    if attempt.reconciliation_state != MpesaAttempt.ReconciliationState.SUCCESS_NEEDS_RECEIPT:
        raise ValidationError({'attempt': 'Only a provider-query success awaiting receipt review can be settled here.'})
    if not AuditLog.objects.filter(
        action='mpesa.stk.reconcile', object_type='MpesaAttempt', object_id=str(attempt.pk),
        metadata__outcome='SUCCESS', metadata__provider_result_code='0', metadata__review_required=True,
    ).exists():
        raise ValidationError({'attempt': 'A successful matching Daraja STK Query audit is required.'})
    if attempt.status not in (MpesaAttempt.Status.INITIATED, MpesaAttempt.Status.STK_SENT):
        raise ValidationError({'attempt': 'This attempt is not open for operator resolution.'})

    if attempt.currency != 'KES' or not attempt.checkout_request_id or not attempt.merchant_request_id:
        raise ValidationError({'attempt': 'The stored checkout is missing required transaction identifiers.'})
    if normalized_evidence['amount_cents'] != attempt.amount_cents:
        raise ValidationError({'amount_cents': 'Provider evidence amount does not match the checkout attempt.'})
    if normalized_evidence['checkout_request_id'] != attempt.checkout_request_id:
        raise ValidationError({'checkout_request_id': 'Provider evidence checkout does not match the attempt.'})
    if normalized_evidence['merchant_request_id'] != attempt.merchant_request_id:
        raise ValidationError({'merchant_request_id': 'Provider evidence merchant request does not match the attempt.'})
    if attempt.account_reference and normalized_evidence['account_reference'] != attempt.account_reference:
        raise ValidationError({'account_reference': 'Provider evidence account reference does not match the attempt.'})
    if phone != attempt.phone_number:
        raise ValidationError({'phone_number': 'Provider evidence phone number does not match the attempt.'})
    try:
        validate_stk_transaction_date(attempt, evidence['transaction_date'])
    except TransactionDateValidationError as error:
        raise ValidationError({'transaction_date': str(error)}) from error
    if not receipt or len(receipt) > 64 or any(character.isspace() for character in receipt):
        raise ValidationError({'receipt': 'Enter a valid M-Pesa receipt number.'})
    if MpesaAttempt.objects.filter(mpesa_receipt_number=receipt).exclude(pk=attempt.pk).exists():
        raise ValidationError({'receipt': 'This receipt is already assigned to another M-Pesa attempt.'})
    if Payment.objects.filter(external_id=receipt).exists():
        raise ValidationError({'receipt': 'This receipt is already recorded against a payment.'})

    try:
        payment = record_payment(
            tenant=attempt.tenant,
            amount_cents=attempt.amount_cents,
            received_date=evidence['transaction_date'],
            method=Payment.Method.MPESA,
            actor=actor,
            reference=receipt,
            external_id=receipt,
            request=request,
        )
    except IntegrityError as error:
        raise ValidationError({'receipt': 'This receipt was concurrently recorded against a payment.'}) from error
    payment = allocate_payment(
        payment, policy_id='CANONICAL_PRIORITY', policy_version=2, actor=actor, request=request,
    )
    attempt.status = MpesaAttempt.Status.SUCCESS
    attempt.result_code = '0'
    attempt.result_description = 'Settled after authorized review of independent provider evidence.'
    attempt.mpesa_receipt_number = receipt
    attempt.reconciliation_state = MpesaAttempt.ReconciliationState.OPERATOR_RESOLVED
    try:
        with transaction.atomic():
            attempt.save(update_fields=(
                'status', 'result_code', 'result_description', 'mpesa_receipt_number',
                'reconciliation_state', 'updated_at',
            ))
    except IntegrityError as error:
        raise ValidationError({'receipt': 'This receipt was concurrently assigned to another attempt.'}) from error
    record_audit(
        action='mpesa.stk.operator_settlement', object_type='MpesaAttempt', object_id=attempt.pk,
        actor=actor, organization=attempt.organization,
        metadata=normalized_evidence, request=request,
    )
    return payment, False
