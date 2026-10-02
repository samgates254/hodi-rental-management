from django.http import FileResponse
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from apps.organizations.models import OrganizationMembership
from apps.leases.models import Lease
from apps.tenants.models import Tenant

from .models import MaintenanceIssue, MaintenanceIssueAttachment, MaintenanceIssueUpdate
from .serializers import (
	MaintenanceIssueCreateSerializer,
	MaintenanceIssueSerializer,
	MaintenanceIssueUpdateSerializer,
)


ISSUE_STAFF_ROLES = (
	OrganizationMembership.Role.OWNER,
	OrganizationMembership.Role.PROPERTY_MANAGER,
	OrganizationMembership.Role.CARETAKER,
)


class MaintenanceIssueViewSet(
	mixins.ListModelMixin,
	mixins.RetrieveModelMixin,
	viewsets.GenericViewSet,
):
	permission_classes = (permissions.IsAuthenticated,)

	def get_queryset(self):
		queryset = MaintenanceIssue.objects.filter(
			Q(
				tenant__organization__memberships__user=self.request.user,
				tenant__organization__memberships__is_active=True,
				tenant__organization__memberships__organization__is_active=True,
				tenant__organization__memberships__role__in=ISSUE_STAFF_ROLES,
			)
			| Q(
				tenant__user=self.request.user,
				tenant__is_active=True,
				tenant__organization__is_active=True,
			)
		).select_related(
			'tenant',
			'unit',
			'unit__building',
			'unit__building__property',
		).prefetch_related(
			'attachments',
			Prefetch(
				'updates',
				queryset=MaintenanceIssueUpdate.objects.select_related('author').order_by('created_at', 'pk'),
			),
		).distinct()
		organization_id = self.request.query_params.get('organization')
		if organization_id:
			try:
				organization_id = int(organization_id)
			except ValueError as error:
				raise serializers.ValidationError({
					'organization': 'A valid organization ID is required.',
				}) from error
			queryset = queryset.filter(tenant__organization_id=organization_id)
		return queryset

	def get_serializer_class(self):
		if self.action == 'create':
			return MaintenanceIssueCreateSerializer
		return MaintenanceIssueSerializer

	@transaction.atomic
	def create(self, request, *args, **kwargs):
		tenant = Tenant.objects.filter(
			user=request.user,
			is_active=True,
			organization__is_active=True,
		).first()
		if tenant is None:
			raise PermissionDenied('A linked tenant account is required to create an issue.')

		data = request.data.copy()
		if not data.get('unit'):
			today = timezone.localdate()
			lease = Lease.objects.filter(
				tenant=tenant,
				status=Lease.Status.ACTIVE,
				start_date__lte=today,
			).filter(
				Q(end_date__isnull=True) | Q(end_date__gte=today),
			).select_related('unit').first()
			if lease is None:
				raise PermissionDenied('An active lease is required to report a maintenance issue.')
			data['unit'] = lease.unit_id

		serializer = self.get_serializer(data=data, context={'request': request, 'tenant': tenant})
		serializer.is_valid(raise_exception=True)
		issue = serializer.save(tenant=tenant)
		MaintenanceIssueUpdate.objects.create(issue=issue, author=request.user, status=issue.status, note='Issue created')
		return Response(
			MaintenanceIssueSerializer(issue, context=self.get_serializer_context()).data,
			status=status.HTTP_201_CREATED,
		)

	@action(detail=True, methods=('post',), url_path='updates')
	@transaction.atomic
	def add_update(self, request, pk=None):
		issue = self.get_object()

		update_serializer = MaintenanceIssueUpdateSerializer(data=request.data)
		update_serializer.is_valid(raise_exception=True)
		values = update_serializer.validated_data
		note = values.get('note', '')
		new_status = values.get('status')
		if not note and new_status is None:
			raise serializers.ValidationError('Provide a note, a status, or both.')
		is_tenant = issue.tenant.user_id == request.user.pk and issue.tenant.is_active
		if is_tenant:
			if new_status is not None:
				raise PermissionDenied('Tenants can add notes but cannot change issue status.')
		else:
			self.ensure_staff_access(issue.organization_id)

		if new_status is not None:
			issue.status = new_status
			issue.resolved_at = timezone.now() if new_status == MaintenanceIssue.Status.RESOLVED else None
			issue.save(update_fields=('status', 'resolved_at', 'updated_at'))
		else:
			issue.save(update_fields=('updated_at',))

		update = MaintenanceIssueUpdate.objects.create(
			issue=issue,
			author=request.user,
			status=new_status,
			note=note,
		)
		return Response(
			MaintenanceIssueUpdateSerializer(update).data,
			status=status.HTTP_201_CREATED,
		)

	def ensure_staff_access(self, organization_id):
		roles = ISSUE_STAFF_ROLES
		if not OrganizationMembership.objects.filter(
			user=self.request.user,
			organization_id=organization_id,
			organization__is_active=True,
			is_active=True,
			role__in=roles,
		).exists():
			raise PermissionDenied('You do not have access to this organization.')

	@action(
		detail=True,
		methods=('get',),
		url_path=r'attachments/(?P<attachment_pk>[^/.]+)',
		url_name='attachment',
	)
	def attachment(self, request, pk=None, attachment_pk=None):
		issue = self.get_object()
		try:
			attachment = issue.attachments.get(pk=attachment_pk)
		except MaintenanceIssueAttachment.DoesNotExist as error:
			raise NotFound('Attachment not found.') from error
		response = FileResponse(
			attachment.file.open('rb'),
			content_type=attachment.content_type,
			filename=attachment.file_name,
		)
		response['X-Content-Type-Options'] = 'nosniff'
		response['Content-Security-Policy'] = "default-src 'none'; sandbox"
		return response
