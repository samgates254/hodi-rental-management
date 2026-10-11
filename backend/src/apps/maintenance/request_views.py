from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.leases.models import Lease
from apps.organizations.models import Organization, OrganizationMembership
from apps.tenants.models import Tenant
from application.services.maintenance import (
    _ensure_legacy_issue,
    accept_assignment,
    add_comment,
    assign_request,
    cancel_request,
    create_request,
    decide_quotation,
    decline_assignment,
    preview_matches,
    schedule_follow_up,
    start_work,
    submit_completion,
    submit_quotation,
    triage_request,
    update_request,
    verify_completion,
)
from common.permissions import (
    organization_ids_for_resource,
    user_can_access_organization_resource,
)

from .models import MaintenanceRequest, RepairCompletion, RepairQuotation, TechnicianProfile, WorkOrder
from .request_serializers import (
    AssignSerializer,
    CommentWriteSerializer,
    MaintenanceCommentSerializer,
    MaintenanceRequestSerializer,
    MaintenanceRequestUpdateSerializer,
    MaintenanceRequestWriteSerializer,
    WorkOrderSerializer,
    TriageSerializer,
    QuotationWriteSerializer,
    QuotationDecisionSerializer,
    RepairQuotationSerializer,
    CompletionWriteSerializer,
    RepairCompletionSerializer,
    VerificationSerializer,
    AssignmentDeclineSerializer,
    FollowUpScheduleSerializer,
)


class MaintenanceRequestPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if organization_ids_for_resource(user, 'maintenance', 'read').exists():
            return True
        if Tenant.objects.filter(user=user, is_active=True, organization__is_active=True).exists():
            return True
        if OrganizationMembership.objects.filter(
            user=user,
            role=OrganizationMembership.Role.TECHNICIAN,
            is_active=True,
            organization__is_active=True,
        ).exists():
            return True
        return WorkOrder.objects.filter(assignee=user).exists()


def _request_queryset(user):
    read_ids = organization_ids_for_resource(user, 'maintenance', 'read')
    return (
        MaintenanceRequest.objects.filter(
            Q(unit__building__property__organization_id__in=read_ids)
            | Q(
                work_order__assignee=user,
                unit__building__property__organization__is_active=True,
                unit__building__property__organization__memberships__user=user,
                unit__building__property__organization__memberships__is_active=True,
                unit__building__property__organization__memberships__role=OrganizationMembership.Role.TECHNICIAN,
            )
            | Q(tenant__user=user, tenant__is_active=True)
        )
        .select_related('unit', 'tenant', 'created_by', 'work_order', 'unit__building__property')
        .prefetch_related('comments')
        .distinct()
    )


ASSIGNABLE_ROLES = (
    OrganizationMembership.Role.OWNER,
    OrganizationMembership.Role.PROPERTY_MANAGER,
    OrganizationMembership.Role.CARETAKER,
    OrganizationMembership.Role.TECHNICIAN,
)


def _staff_write(user, organization_id):
    return user_can_access_organization_resource(user, organization_id, 'maintenance', 'write')


class MaintenanceRequestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated, MaintenanceRequestPermission)
    http_method_names = ('get', 'post', 'patch', 'head', 'options')

    def get_queryset(self):
        return _request_queryset(self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return MaintenanceRequestWriteSerializer
        if self.action in ('partial_update', 'update'):
            return MaintenanceRequestUpdateSerializer
        return MaintenanceRequestSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = MaintenanceRequestWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tenant_record = Tenant.objects.filter(
            user=request.user,
            is_active=True,
            organization__is_active=True,
        ).first()
        unit = data.get('unit')
        tenant = data.get('tenant')
        if tenant_record is not None and not _staff_write(
            request.user,
            tenant_record.organization_id,
        ):
            tenant = tenant_record
            if unit is None:
                today = timezone.localdate()
                lease = Lease.objects.filter(
                    tenant=tenant_record,
                    status=Lease.Status.ACTIVE,
                    start_date__lte=today,
                ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today)).select_related('unit').first()
                if lease is None:
                    raise PermissionDenied('An active lease is required to report a maintenance issue.')
                unit = lease.unit
        elif unit is None:
            raise ValidationError({'unit': 'A unit is required.'})
        else:
            if not _staff_write(request.user, unit.organization_id):
                raise PermissionDenied('You do not have permission for this organization.')
            if tenant is not None and tenant.organization_id != unit.organization_id:
                raise ValidationError({'tenant': 'Tenant and unit must belong to the same organization.'})
        maintenance_request = create_request(
            unit=unit,
            tenant=tenant,
            title=data['title'],
            description=data['description'],
            hazard=data['hazard'],
            category=data.get('category', 'OTHER'),
            requires_approval=data.get('requires_approval', False) if _staff_write(request.user, unit.organization_id) else False,
            vulnerability=data.get('vulnerability', 1),
            building_age_years=data.get('building_age_years'),
            age_band_value=data.get('age_band_value'),
            actor=request.user,
            request=request,
        )
        _ensure_legacy_issue(maintenance_request, actor=request.user)
        return Response(
            MaintenanceRequestSerializer(maintenance_request, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        maintenance_request = self.get_object()
        if not _staff_write(request.user, maintenance_request.organization_id):
            raise PermissionDenied('You do not have permission for this organization.')
        serializer = MaintenanceRequestUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        maintenance_request = update_request(
            maintenance_request,
            validated_data=serializer.validated_data,
            actor=request.user,
            request=request,
        )
        return Response(MaintenanceRequestSerializer(maintenance_request, context={'request': request}).data)

    @action(detail=True, methods=('post',), url_path='triage')
    def triage(self, request, pk=None):
        row = self.get_object()
        if not _staff_write(request.user, row.organization_id):
            raise PermissionDenied('You do not have permission to triage this request.')
        serializer = TriageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = triage_request(row, actor=request.user, request=request, **serializer.validated_data)
        return Response(MaintenanceRequestSerializer(row, context={'request': request}).data)

    def update(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    @action(detail=True, methods=('post',), url_path='assign')
    def assign(self, request, pk=None):
        maintenance_request = self.get_object()
        if not _staff_write(request.user, maintenance_request.organization_id):
            raise PermissionDenied('You do not have permission for this organization.')
        serializer = AssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        supplied_user_id = 'user_id' in serializer.validated_data
        field_name = 'user_id' if supplied_user_id else 'technician_id'
        user_id = serializer.validated_data.get('user_id', serializer.validated_data.get('technician_id'))
        assignee = get_user_model().objects.filter(pk=user_id, is_active=True).first()
        membership = OrganizationMembership.objects.filter(
            user=assignee,
            organization_id=maintenance_request.organization_id,
            organization__is_active=True,
            is_active=True,
            role__in=ASSIGNABLE_ROLES,
        ).first() if assignee is not None else None
        if membership is None:
            raise ValidationError({
                field_name: 'Assignee must be an active maintenance member of this organization.',
            })
        if membership.role == OrganizationMembership.Role.TECHNICIAN:
            profile = TechnicianProfile.objects.filter(user=assignee).first()
            if profile is None or not profile.verified or not profile.available:
                raise ValidationError({
                    field_name: 'Technicians must have a verified, available technician profile.',
                })
        maintenance_request = assign_request(
            maintenance_request,
            assignee=assignee,
            notes=serializer.validated_data.get('notes', ''),
            actor=request.user,
            request=request,
        )
        return Response(MaintenanceRequestSerializer(maintenance_request, context={'request': request}).data)

    @action(detail=True, methods=('post',), url_path='start')
    def start(self, request, pk=None):
        row = self.get_object()
        order = start_work(row, actor=request.user, request=request)
        return Response(WorkOrderSerializer(order, context={'request': request}).data)

    @action(detail=True, methods=('post',), url_path='accept')
    def accept(self, request, pk=None):
        row = self.get_object()
        accept_assignment(row, actor=request.user, request=request)
        return Response(WorkOrderSerializer(row.work_order, context={'request': request}).data)

    @action(detail=True, methods=('post',), url_path='decline')
    def decline(self, request, pk=None):
        row = self.get_object()
        serializer = AssignmentDeclineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decline_assignment(row, actor=request.user, request=request, **serializer.validated_data)
        row.refresh_from_db()
        return Response(MaintenanceRequestSerializer(row, context={'request': request}).data)

    @action(detail=True, methods=('post',), url_path='follow-up')
    def follow_up(self, request, pk=None):
        row = self.get_object()
        if not _staff_write(request.user, row.organization_id):
            raise PermissionDenied('Only authorized maintenance staff can schedule repair follow-up.')
        serializer = FollowUpScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        assignee_id = data.get('assignee_id', row.work_order.assignee_id)
        assignee = get_user_model().objects.filter(pk=assignee_id, is_active=True).first() if assignee_id else None
        if assignee is None:
            raise ValidationError({'assignee_id': 'Choose an active maintenance member.'})
        row = schedule_follow_up(
            row, actor=request.user, follow_up_at=data['follow_up_at'], reason=data['reason'],
            assignee=assignee, request=request,
        )
        return Response(MaintenanceRequestSerializer(row, context={'request': request}).data)

    @action(detail=True, methods=('get', 'post'), url_path='quotations')
    def quotations(self, request, pk=None):
        row = self.get_object()
        if request.method == 'GET':
            quotes = row.work_order.quotations.all()
            if row.tenant_id and row.tenant.user_id == request.user.id:
                quotes = quotes.filter(status='APPROVED')
            return Response(RepairQuotationSerializer(quotes, many=True, context={'request': request}).data)
        if not _staff_write(request.user, row.organization_id) and row.work_order.assignee_id != request.user.id:
            raise PermissionDenied('Only assigned technicians or maintenance staff can submit a quotation.')
        serializer = QuotationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        quote = submit_quotation(
            row.work_order, actor=request.user,
            labour=data['labour_estimate_cents'], materials=data['materials_estimate_cents'],
            other=data['other_estimate_cents'], explanation=data['explanation'], request=request,
        )
        return Response(RepairQuotationSerializer(quote, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=('post',), url_path=r'quotations/(?P<quotation_id>[^/.]+)/decision')
    def quotation_decision(self, request, pk=None, quotation_id=None):
        row = self.get_object()
        if not _staff_write(request.user, row.organization_id):
            raise PermissionDenied('Only authorized maintenance staff can decide quotations.')
        try:
            quote = row.work_order.quotations.get(pk=quotation_id)
        except RepairQuotation.DoesNotExist as error:
            raise NotFound('Quotation not found.') from error
        serializer = QuotationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data
        quote = decide_quotation(
            quote, actor=request.user, approve=decision['approved'], notes=decision.get('notes', ''), request=request,
        )
        return Response(RepairQuotationSerializer(quote, context={'request': request}).data)

    @action(detail=True, methods=('post',), url_path='complete')
    def complete(self, request, pk=None):
        maintenance_request = self.get_object()
        work_order = maintenance_request.work_order
        is_assignee = work_order.assignee_id == request.user.id
        if not is_assignee and not _staff_write(request.user, maintenance_request.organization_id):
            raise PermissionDenied('You do not have permission for this organization.')
        if not is_assignee:
            raise PermissionDenied('Only the assigned technician can submit completion.')
        serializer = CompletionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        completion = submit_completion(
            work_order, actor=request.user, data=serializer.validated_data,
            materials=serializer.validated_data.pop('materials', []), request=request,
        )
        return Response(RepairCompletionSerializer(completion, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=('post',), url_path='verify')
    def verify(self, request, pk=None):
        row = self.get_object()
        if not _staff_write(request.user, row.organization_id):
            raise PermissionDenied('Only authorized maintenance staff can verify repairs.')
        serializer = VerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        completion_id = request.data.get('completion_id')
        try:
            completion = row.work_order.completions.get(pk=completion_id)
        except RepairCompletion.DoesNotExist as error:
            raise NotFound('Completion record not found.') from error
        completion = verify_completion(completion, actor=request.user, request=request, **serializer.validated_data)
        return Response(RepairCompletionSerializer(completion, context={'request': request}).data)

    @action(detail=True, methods=('post',), url_path='close')
    def close(self, request, pk=None):
        maintenance_request = self.get_object()
        if not _staff_write(request.user, maintenance_request.organization_id):
            raise PermissionDenied('You do not have permission for this organization.')
        completion = maintenance_request.work_order.completions.filter(status='SUBMITTED').order_by('-submitted_at').first()
        if completion is None:
            raise ValidationError({'completion': 'A submitted repair outcome is required before verification.'})
        completion = verify_completion(
            completion, actor=request.user, approved=True,
            notes=request.data.get('notes', '') if isinstance(request.data, dict) else '', request=request,
        )
        return Response(RepairCompletionSerializer(completion, context={'request': request}).data)

    @action(detail=True, methods=('post',), url_path='cancel')
    def cancel(self, request, pk=None):
        row = self.get_object()
        if not _staff_write(request.user, row.organization_id):
            raise PermissionDenied('Only maintenance staff can cancel a request.')
        reason = request.data.get('reason', '') if isinstance(request.data, dict) else ''
        row = cancel_request(row, actor=request.user, reason=reason, request=request)
        return Response(MaintenanceRequestSerializer(row, context={'request': request}).data)

    @action(detail=True, methods=('get', 'post'), url_path='comments')
    def comments(self, request, pk=None):
        maintenance_request = self.get_object()
        if request.method == 'GET':
            rows = maintenance_request.comments.select_related('author')
            return Response(MaintenanceCommentSerializer(rows, many=True).data)
        is_tenant = maintenance_request.tenant_id and maintenance_request.tenant.user_id == request.user.id
        is_assignee = maintenance_request.work_order.assignee_id == request.user.id
        if not is_tenant and not is_assignee and not _staff_write(request.user, maintenance_request.organization_id):
            if not user_can_access_organization_resource(
                request.user,
                maintenance_request.organization_id,
                'maintenance',
                'read',
            ):
                raise PermissionDenied('You do not have permission for this organization.')
        serializer = CommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = add_comment(
            maintenance_request,
            author=request.user,
            body=serializer.validated_data['body'],
        )
        return Response(MaintenanceCommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class WorkOrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated, MaintenanceRequestPermission)
    serializer_class = WorkOrderSerializer

    def get_queryset(self):
        visible = _request_queryset(self.request.user).values_list('pk', flat=True)
        return WorkOrder.objects.filter(request_id__in=visible).select_related('request', 'assignee')


class MatchPreviewView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        organization_id = request.data.get('organization')
        try:
            organization = Organization.objects.get(pk=int(organization_id), is_active=True)
        except (Organization.DoesNotExist, TypeError, ValueError) as error:
            raise ValidationError({'organization': 'An active organization is required.'}) from error
        if not user_can_access_organization_resource(request.user, organization.pk, 'maintenance', 'read'):
            raise PermissionDenied('You do not have permission for this organization.')
        jobs = request.data.get('jobs') or []
        if not isinstance(jobs, list):
            raise ValidationError({'jobs': 'jobs must be a list.'})
        return Response(preview_matches(organization=organization, jobs=jobs))
