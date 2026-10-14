import hmac
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from application.services.mpesa import initiate_mpesa_stk
from application.services.mpesa_callback import (
    CallbackValidationError,
    TransactionDateValidationError,
    classify_stk_query,
    parse_stk_callback,
    settle_verified_stk_failure,
    settle_stk_callback,
    validate_stk_success_callback,
)
from application.services.mpesa_review import resolve_mpesa_attempt_from_evidence
from application.services.audit import record_audit
from infrastructure.payments.mpesa import MpesaClient, MpesaError

from .models import MpesaAttempt
from .serializers_mpesa import (
    MpesaAttemptSerializer, MpesaAttemptStatusSerializer, MpesaInitiateSerializer,
    MpesaOperatorEvidenceSerializer,
)

logger = logging.getLogger(__name__)


class MpesaInitiateView(APIView):
    """Tenant-only STK Push initiation. Does not settle a Payment."""

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = MpesaInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attempt = initiate_mpesa_stk(
            actor=request.user,
            amount_cents=serializer.validated_data['amount_cents'],
            phone_number=serializer.validated_data.get('phone_number') or '',
            invoice_id=serializer.validated_data.get('invoice'),
            idempotency_key=str(serializer.validated_data['idempotency_key']) if serializer.validated_data.get('idempotency_key') else None,
            request=request,
        )
        payload = MpesaAttemptSerializer(attempt).data
        if attempt.status in (MpesaAttempt.Status.STK_SENT, MpesaAttempt.Status.INITIATED):
            return Response(payload, status=status.HTTP_202_ACCEPTED)
        return Response(payload, status=status.HTTP_400_BAD_REQUEST)


def _callback_authorized(request, path_token=None) -> bool:
    expected = settings.MPESA_CALLBACK_AUTH_TOKEN
    if not expected:
        return False
    header = request.headers.get('X-Hodi-Mpesa-Callback-Secret', '') or ''
    provided = path_token or header
    if not provided:
        return False
    return hmac.compare_digest(str(provided), expected)


class MpesaCallbackView(APIView):
    """Daraja callback gated by a bearer token; Daraja sends no signature."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request, callback_token=None):
        if not settings.MPESA_CALLBACK_AUTH_TOKEN:
            logger.error('Daraja callback rejected: callback token is not configured')
            return Response({'detail': 'Callback authentication is not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not _callback_authorized(request, callback_token):
            logger.warning('Daraja STK callback rejected: missing or invalid callback token')
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            stk = parse_stk_callback(request.data)
            checkout = str(stk.get('CheckoutRequestID') or '').strip()
            merchant = str(stk.get('MerchantRequestID') or '').strip()
            callback_code = str(stk.get('ResultCode')).strip()
            attempt = MpesaAttempt.objects.filter(checkout_request_id=checkout).first()
            if attempt is None:
                result = settle_stk_callback(payload=request.data, request=request)
                return Response({'detail': result.detail, 'matched': result.matched, 'settled': False,
                                 'duplicate': result.duplicate, 'status': result.status}, status=200)
            if not attempt.merchant_request_id or merchant != attempt.merchant_request_id:
                record_audit(
                    action='mpesa.stk.callback_discrepancy', object_type='MpesaAttempt',
                    object_id=attempt.pk, actor=attempt.initiated_by, organization=attempt.organization,
                    metadata={'reason': 'merchant_reference_mismatch'}, request=request,
                )
                return Response({'detail': 'Callback references are inconsistent; no payment state changed.',
                                 'matched': True, 'settled': False, 'duplicate': False,
                                 'status': 'UNRESOLVED'}, status=202)

            query = MpesaClient.from_settings().stk_query(checkout_request_id=checkout)
            query_outcome, query_code, query_description = classify_stk_query(attempt, query)
            if query_outcome == 'UNRESOLVED':
                record_audit(
                    action='mpesa.stk.callback_discrepancy', object_type='MpesaAttempt',
                    object_id=attempt.pk, actor=attempt.initiated_by, organization=attempt.organization,
                    metadata={'reason': 'query_unresolved'}, request=request,
                )
                return Response({'detail': 'Provider outcome is unresolved; no payment state changed.',
                                 'matched': True, 'settled': False, 'duplicate': False,
                                 'status': 'UNRESOLVED'}, status=202)
            if query_code != callback_code:
                record_audit(
                    action='mpesa.stk.callback_discrepancy', object_type='MpesaAttempt',
                    object_id=attempt.pk, actor=attempt.initiated_by, organization=attempt.organization,
                    metadata={'reason': 'callback_provider_outcome_mismatch', 'provider_result_code': query_code},
                    request=request,
                )
                return Response({'detail': 'Callback and provider outcomes conflict; no payment state changed.',
                                 'matched': True, 'settled': False, 'duplicate': False,
                                 'status': 'UNRESOLVED'}, status=202)

            if callback_code == '0':
                try:
                    validate_stk_success_callback(attempt, request.data)
                except TransactionDateValidationError:
                    # Persist the reconciliation marker through the same locked
                    # settlement path, which guarantees no financial writes.
                    result = settle_stk_callback(payload=request.data, provider_query=query, request=request)
                    return Response({
                        'detail': result.detail,
                        'matched': result.matched,
                        'settled': result.settled,
                        'duplicate': result.duplicate,
                        'status': result.status,
                    }, status=status.HTTP_202_ACCEPTED)
                except CallbackValidationError:
                    record_audit(
                        action='mpesa.stk.callback_discrepancy', object_type='MpesaAttempt',
                        object_id=attempt.pk, actor=attempt.initiated_by, organization=attempt.organization,
                        metadata={'reason': 'success_metadata_mismatch'}, request=request,
                    )
                    return Response({
                        'detail': 'Callback failed validation; no payment was recorded.',
                        'matched': True, 'settled': False, 'duplicate': False, 'status': 'UNRESOLVED',
                    }, status=status.HTTP_202_ACCEPTED)
                result = settle_stk_callback(payload=request.data, provider_query=query, request=request)
            else:
                result = settle_verified_stk_failure(
                    checkout_request_id=checkout,
                    merchant_request_id=merchant,
                    result_code=query_code,
                    result_description=query_description or str(stk.get('ResultDesc') or ''),
                    provider_query=query,
                    request=request,
                )
        except MpesaError:
            logger.warning('Daraja callback could not be independently verified; no payment was posted')
            return Response({'detail': 'Provider outcome is unresolved; no payment was posted.',
                             'matched': False, 'settled': False, 'duplicate': False,
                             'status': 'UNRESOLVED'}, status=202)
        except ValidationError as error:
            return Response(error.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                'detail': result.detail,
                'matched': result.matched,
                'settled': result.settled,
                'duplicate': result.duplicate,
                'status': result.status,
            },
            status=status.HTTP_200_OK,
        )


class MpesaAttemptStatusView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, attempt_id):
        attempt = MpesaAttempt.objects.filter(
            tenant__user=request.user, tenant__is_active=True,
            tenant__organization__is_active=True, pk=attempt_id,
        ).first()
        if attempt is None:
            raise NotFound('Payment attempt not found.')
        return Response(MpesaAttemptStatusSerializer(attempt).data)


class MpesaOperatorResolutionView(APIView):
    """Settle query-confirmed receipts after organization staff evidence review."""

    permission_classes = (IsAuthenticated,)

    def post(self, request, attempt_id):
        serializer = MpesaOperatorEvidenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment, duplicate = resolve_mpesa_attempt_from_evidence(
            attempt_id=attempt_id, actor=request.user,
            evidence=serializer.validated_data, request=request,
        )
        return Response({
            'attempt_id': str(attempt_id), 'payment_id': str(payment.pk),
            'receipt': payment.external_id, 'status': payment.status,
            'settled': True, 'duplicate': duplicate,
        })
