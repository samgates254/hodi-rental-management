from datetime import datetime

from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Tenant
from application.services.billing import (
    add_charge,
    allocate_payment,
    assess_tenant_delinquency,
    create_invoice,
    post_invoice,
    record_payment,
    update_draft_invoice,
    void_invoice,
)
from common.permissions import (
    organization_ids_for_resource,
    user_can_access_organization_resource,
)

from .models import Charge, Invoice, Payment
from .serializers_ledger import (
    AllocateSerializer,
    ChargeSerializer,
    ChargeWriteSerializer,
    InvoiceSerializer,
    InvoiceUpdateSerializer,
    InvoiceWriteSerializer,
    PaymentSerializer,
    PaymentWriteSerializer,
)


class BillingAccess(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        action = 'read' if request.method in ('GET', 'HEAD', 'OPTIONS') else 'write'
        if organization_ids_for_resource(user, 'billing', action).exists():
            return True
        if action == 'read' and Tenant.objects.filter(
            user=user,
            is_active=True,
            organization__is_active=True,
        ).exists():
            return True
        return False


def _readable_billing_orgs(user):
    return organization_ids_for_resource(user, 'billing', 'read')


def _ensure_billing_write(user, organization_id):
    if not user_can_access_organization_resource(user, organization_id, 'billing', 'write'):
        raise PermissionDenied('You do not have permission for this organization.')


def _invoice_queryset(user):
    return Invoice.objects.filter(
        Q(organization_id__in=_readable_billing_orgs(user))
        | Q(tenant__user=user, tenant__is_active=True)
    ).distinct().prefetch_related('charges')


def _charge_queryset(user):
    return Charge.objects.filter(
        Q(organization_id__in=_readable_billing_orgs(user))
        | Q(tenant__user=user, tenant__is_active=True)
    ).distinct()


def _payment_queryset(user):
    return Payment.objects.filter(
        Q(organization_id__in=_readable_billing_orgs(user))
        | Q(tenant__user=user, tenant__is_active=True)
    ).distinct().prefetch_related('allocations', 'postings')


class InvoiceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated, BillingAccess)
    http_method_names = ('get', 'post', 'patch', 'head', 'options')

    def get_queryset(self):
        return _invoice_queryset(self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return InvoiceWriteSerializer
        if self.action in ('partial_update', 'update'):
            return InvoiceUpdateSerializer
        return InvoiceSerializer

    def create(self, request, *args, **kwargs):
        serializer = InvoiceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = serializer.validated_data['tenant']
        _ensure_billing_write(request.user, tenant.organization_id)
        invoice = create_invoice(
            tenant=tenant,
            lease=serializer.validated_data.get('lease'),
            period_start=serializer.validated_data['period_start'],
            period_end=serializer.validated_data['period_end'],
            due_date=serializer.validated_data['due_date'],
            notes=serializer.validated_data.get('notes', ''),
            include_rent=serializer.validated_data.get('include_rent'),
            generation_key=serializer.validated_data.get('generation_key', ''),
            actor=request.user,
            request=request,
        )
        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        invoice = self.get_object()
        _ensure_billing_write(request.user, invoice.organization_id)
        serializer = InvoiceUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        invoice = update_draft_invoice(invoice, validated_data=serializer.validated_data)
        return Response(InvoiceSerializer(invoice).data)

    def update(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    @action(detail=True, methods=('post',), url_path='post')
    def post_invoice(self, request, pk=None):
        invoice = self.get_object()
        _ensure_billing_write(request.user, invoice.organization_id)
        invoice = post_invoice(invoice, actor=request.user, request=request)
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=('post',), url_path='void')
    def void(self, request, pk=None):
        invoice = self.get_object()
        _ensure_billing_write(request.user, invoice.organization_id)
        invoice = void_invoice(invoice, actor=request.user, request=request)
        return Response(InvoiceSerializer(invoice).data)


class ChargeViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated, BillingAccess)
    serializer_class = ChargeSerializer

    def get_queryset(self):
        return _charge_queryset(self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = ChargeWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = serializer.validated_data['invoice']
        if not _invoice_queryset(request.user).filter(pk=invoice.pk).exists():
            raise NotFound('Invoice not found.')
        _ensure_billing_write(request.user, invoice.organization_id)
        charge = add_charge(
            invoice=invoice,
            charge_type=serializer.validated_data['charge_type'],
            amount_cents=serializer.validated_data['amount_cents'],
            due_date=serializer.validated_data['due_date'],
            period_start=serializer.validated_data.get('period_start'),
            description=serializer.validated_data.get('description', ''),
            actor=request.user,
        )
        return Response(ChargeSerializer(charge).data, status=status.HTTP_201_CREATED)


class PaymentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated, BillingAccess)

    def get_queryset(self):
        return _payment_queryset(self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentWriteSerializer
        return PaymentSerializer

    def create(self, request, *args, **kwargs):
        serializer = PaymentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = serializer.validated_data['tenant']
        _ensure_billing_write(request.user, tenant.organization_id)
        payment = record_payment(
            tenant=tenant,
            amount_cents=serializer.validated_data['amount_cents'],
            received_date=serializer.validated_data['received_date'],
            method=serializer.validated_data['method'],
            reference=serializer.validated_data.get('reference', ''),
            external_id=serializer.validated_data.get('external_id', ''),
            actor=request.user,
            request=request,
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=('post',), url_path='allocate')
    def allocate(self, request, pk=None):
        payment = self.get_object()
        _ensure_billing_write(request.user, payment.organization_id)
        serializer = AllocateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = allocate_payment(
            payment,
            policy_id=serializer.validated_data['policy_id'],
            policy_version=serializer.validated_data['policy_version'],
            actor=request.user,
            request=request,
        )
        return Response(PaymentSerializer(payment).data)


class DelinquencyView(APIView):
    permission_classes = (IsAuthenticated, BillingAccess)

    def get(self, request):
        tenant_raw = request.query_params.get('tenant')
        as_of_raw = request.query_params.get('as_of')
        if not tenant_raw or not as_of_raw:
            raise ValidationError({
                'detail': 'tenant and as_of are required.',
            })
        try:
            tenant = Tenant.objects.get(pk=int(tenant_raw))
        except (Tenant.DoesNotExist, ValueError) as error:
            raise NotFound('Tenant not found.') from error
        can_read = user_can_access_organization_resource(
            request.user,
            tenant.organization_id,
            'billing',
            'read',
        ) or tenant.user_id == request.user.id
        if not can_read:
            raise NotFound('Tenant not found.')
        try:
            as_of = datetime.strptime(as_of_raw, '%Y-%m-%d').date()
        except ValueError as error:
            raise ValidationError({'as_of': 'Use YYYY-MM-DD.'}) from error
        grace_raw = request.query_params.get('grace_days', '0')
        try:
            grace_days = int(grace_raw)
        except ValueError as error:
            raise ValidationError({'grace_days': 'grace_days must be an integer.'}) from error
        return Response(assess_tenant_delinquency(tenant=tenant, as_of=as_of, grace_days=grace_days))
