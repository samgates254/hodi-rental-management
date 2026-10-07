from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from application.services.mpesa import initiate_mpesa_stk

from .models import MpesaAttempt
from .serializers_mpesa import MpesaAttemptSerializer, MpesaInitiateSerializer


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
