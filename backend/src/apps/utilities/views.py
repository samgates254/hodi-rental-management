from django.db import IntegrityError, models, transaction
from django.db.models import Exists, OuterRef
from rest_framework import mixins, status, viewsets
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from application.services.audit import record_audit
from common.permissions import (
    OrganizationRolePermission,
    organization_ids_for_resource,
    user_can_access_organization_resource,
)
from common.rental_dates import rental_business_date

from .models import UtilityAccount, UtilityBill
from .serializers import UtilityAccountSerializer, UtilityBillSerializer


class TenantUtilityView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        from apps.leases.models import Lease
        try:
            tenant = request.user.tenant_record
        except Exception:
            return Response([])
        if not tenant.is_active or not tenant.organization.is_active:
            return Response([])
        today = rental_business_date()
        # Utility bills are unit-level records, so only expose a bill to a
        # tenant when its entire inclusive billing period belongs to one of
        # that tenant's current active leases. A bill spanning a lease change
        # cannot be safely assigned to either tenant without an allocation.
        authorized_lease = Lease.objects.filter(
            tenant=tenant,
            unit_id=OuterRef('account__unit_id'),
            status='ACTIVE',
            start_date__lte=today,
        ).filter(start_date__lte=OuterRef('period_start')).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=today),
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=OuterRef('period_end')),
        )
        bills = UtilityBill.objects.filter(
            account__responsible_party=UtilityAccount.ResponsibleParty.TENANT,
            account__is_active=True,
        ).filter(
            Exists(authorized_lease),
        ).select_related('account__property', 'account__unit')
        return Response([{
            'id': bill.pk, 'utility_type': bill.account.get_service_type_display(),
            'service_description': bill.account.property.name,
            'unit': bill.account.unit.name if bill.account.unit_id else None,
            'period_start': bill.period_start, 'period_end': bill.period_end,
            'reading_start': bill.reading_start, 'reading_end': bill.reading_end,
            'reading_unit': bill.reading_unit, 'amount_minor': bill.amount_minor,
            'currency': bill.currency, 'due_date': bill.due_date,
            'status': 'RECORDED', 'document_available': bool(bill.document_reference),
        } for bill in bills])


class UtilityWriteReadViewSet:
    permission_classes = (IsAuthenticated, OrganizationRolePermission)
    organization_resource = 'utilities'

    def readable_organization_ids(self):
        return organization_ids_for_resource(self.request.user, 'utilities', 'read')

    def ensure_write(self, organization_id):
        if not user_can_access_organization_resource(
            self.request.user, organization_id, 'utilities', 'write',
        ):
            raise PermissionDenied('You do not have permission to manage utilities for this organization.')


class UtilityAccountViewSet(
    UtilityWriteReadViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = UtilityAccountSerializer
    http_method_names = ('get', 'post', 'head', 'options')

    def get_queryset(self):
        rows = UtilityAccount.objects.filter(organization_id__in=self.readable_organization_ids())
        organization_id = self.request.query_params.get('organization')
        return rows.filter(organization_id=organization_id) if organization_id else rows

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = serializer.validated_data['organization']
        self.ensure_write(organization.pk)
        account = serializer.save(created_by=request.user)
        record_audit(
            action='utility.account.create',
            object_type='UtilityAccount',
            object_id=account.pk,
            actor=request.user,
            organization=organization,
            metadata={'service_type': account.service_type, 'responsible_party': account.responsible_party},
            request=request,
        )
        return Response(self.get_serializer(account).data, status=status.HTTP_201_CREATED)


class UtilityBillViewSet(
    UtilityWriteReadViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = UtilityBillSerializer
    http_method_names = ('get', 'post', 'head', 'options')

    def get_queryset(self):
        rows = UtilityBill.objects.filter(
            account__organization_id__in=self.readable_organization_ids(),
        ).select_related('account', 'account__property', 'account__unit')
        organization_id = self.request.query_params.get('organization')
        return rows.filter(account__organization_id=organization_id) if organization_id else rows

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = serializer.validated_data['account']
        self.ensure_write(account.organization_id)
        try:
            with transaction.atomic():
                bill = serializer.save(recorded_by=request.user)
        except IntegrityError as error:
            raise ValidationError({'period_start': 'A bill is already recorded for this account and period.'}) from error
        record_audit(
            action='utility.bill.record',
            object_type='UtilityBill',
            object_id=bill.pk,
            actor=request.user,
            organization=account.organization,
            metadata={
                'account_id': account.pk,
                'amount_minor': bill.amount_minor,
                'responsible_party': account.responsible_party,
            },
            request=request,
        )
        return Response(self.get_serializer(bill).data, status=status.HTTP_201_CREATED)
