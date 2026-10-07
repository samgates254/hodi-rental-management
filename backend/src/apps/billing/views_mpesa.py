import hmac
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from application.services.mpesa import initiate_mpesa_stk
from application.services.mpesa_callback import settle_stk_callback

from .models import MpesaAttempt
from .serializers_mpesa import MpesaAttemptSerializer, MpesaInitiateSerializer

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
            request=request,
        )
        payload = MpesaAttemptSerializer(attempt).data
        if attempt.status == MpesaAttempt.Status.STK_SENT:
            return Response(payload, status=status.HTTP_202_ACCEPTED)
        return Response(payload, status=status.HTTP_400_BAD_REQUEST)


def _callback_authorized(request, path_token=None) -> bool:
    expected = settings.MPESA_CALLBACK_AUTH_TOKEN
    if not expected:
        return True
    header = request.headers.get('X-Hodi-Mpesa-Callback-Secret', '') or ''
    provided = path_token or header
    if not provided:
        return False
    return hmac.compare_digest(str(provided), expected)


class MpesaCallbackView(APIView):
    """Daraja STK callback. Unsigned; gated by HTTPS URL plus optional path token."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request, callback_token=None):
        if not _callback_authorized(request, callback_token):
            logger.warning('Daraja STK callback rejected: missing or invalid callback token')
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            result = settle_stk_callback(payload=request.data, request=request)
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
