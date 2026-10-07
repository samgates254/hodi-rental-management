from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.tenants.models import Tenant
from application.services.leases import activate_lease, expire_lease, terminate_lease
from common.permissions import (
	organization_ids_for_resource,
	user_can_access_organization_resource,
)

from .models import Lease, LeaseAmendment, RentSchedule
from .serializers import (
	LeaseAmendmentSerializer,
	LeaseSerializer,
	LeaseTerminateSerializer,
	RentScheduleSerializer,
)


class LeaseAccess(BasePermission):
	"""Staff use organization roles. Tenants may read only their own leases."""

	def has_permission(self, request, view):
		user = request.user
		if not user or not user.is_authenticated:
			return False
		action = 'read' if request.method in ('GET', 'HEAD', 'OPTIONS') else 'write'
		if organization_ids_for_resource(user, 'leases', action).exists():
			return True
		return action == 'read' and Tenant.objects.filter(
			user=user,
			is_active=True,
			organization__is_active=True,
		).exists()

	def has_object_permission(self, request, view, obj):
		user = request.user
		action = 'read' if request.method in ('GET', 'HEAD', 'OPTIONS') else 'write'
		organization_id = getattr(obj, 'organization_id', None)
		if organization_id is None and getattr(obj, 'lease', None) is not None:
			organization_id = obj.lease.organization_id
		if organization_id is not None and user_can_access_organization_resource(
			user,
			organization_id,
			'leases',
			action,
		):
			return True
		tenant = getattr(obj, 'tenant', None)
		if tenant is None and getattr(obj, 'lease', None) is not None:
			tenant = obj.lease.tenant
		return (
			action == 'read'
			and tenant is not None
			and tenant.user_id == user.id
			and tenant.is_active
		)


class LeaseScopedViewSet(viewsets.ModelViewSet):
	permission_classes = (IsAuthenticated, LeaseAccess)
	organization_resource = 'leases'

	def access_action(self):
		return 'read' if self.request.method in ('GET', 'HEAD', 'OPTIONS') else 'write'

	def allowed_organization_ids(self):
		return organization_ids_for_resource(
			self.request.user,
			self.organization_resource,
			self.access_action(),
		)

	def ensure_allowed(self, organization_id):
		if not user_can_access_organization_resource(
			self.request.user,
			organization_id,
			self.organization_resource,
			self.access_action(),
		):
			raise PermissionDenied('You do not have permission for this organization.')


class LeaseViewSet(LeaseScopedViewSet):
	serializer_class = LeaseSerializer

	def get_queryset(self):
		queryset = Lease.objects.filter(
			tenant__organization_id__in=self.allowed_organization_ids(),
		)
		if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
			queryset = queryset | Lease.objects.filter(
				tenant__user=self.request.user,
				tenant__is_active=True,
				tenant__organization__is_active=True,
			)
			queryset = queryset.distinct()
		return queryset.select_related(
			'tenant', 'tenant__organization', 'unit', 'unit__building', 'unit__building__property',
		)

	def perform_create(self, serializer):
		tenant = serializer.validated_data['tenant']
		self.ensure_allowed(tenant.organization_id)
		self.save_and_validate(serializer)

	def perform_update(self, serializer):
		tenant = serializer.validated_data.get('tenant', serializer.instance.tenant)
		self.ensure_allowed(tenant.organization_id)
		self.save_and_validate(serializer)

	@transaction.atomic
	def save_and_validate(self, serializer):
		instance = serializer.save()
		try:
			instance.full_clean()
		except DjangoValidationError as error:
			raise ValidationError(error.message_dict) from error

	@action(detail=True, methods=('post',))
	def activate(self, request, pk=None):
		lease = activate_lease(self.get_object(), actor=request.user, request=request)
		return Response(LeaseSerializer(lease).data)

	@action(detail=True, methods=('post',))
	def terminate(self, request, pk=None):
		serializer = LeaseTerminateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		lease = terminate_lease(
			self.get_object(),
			end_date=serializer.validated_data['end_date'],
			reason=serializer.validated_data.get('reason', ''),
			actor=request.user,
			request=request,
		)
		return Response(LeaseSerializer(lease).data)

	@action(detail=True, methods=('post',))
	def expire(self, request, pk=None):
		lease = expire_lease(self.get_object(), actor=request.user, request=request)
		return Response(LeaseSerializer(lease).data)


class RentScheduleViewSet(LeaseScopedViewSet):
	serializer_class = RentScheduleSerializer

	def get_queryset(self):
		return RentSchedule.objects.filter(
			lease__tenant__organization_id__in=self.allowed_organization_ids(),
		).select_related('lease')

	def perform_create(self, serializer):
		lease = serializer.validated_data['lease']
		self.ensure_allowed(lease.organization_id)
		self.save_and_validate(serializer)

	def perform_update(self, serializer):
		lease = serializer.validated_data.get('lease', serializer.instance.lease)
		self.ensure_allowed(lease.organization_id)
		self.save_and_validate(serializer)

	@transaction.atomic
	def save_and_validate(self, serializer):
		instance = serializer.save()
		try:
			instance.full_clean()
		except DjangoValidationError as error:
			raise ValidationError(error.message_dict) from error


class LeaseAmendmentViewSet(LeaseScopedViewSet):
	serializer_class = LeaseAmendmentSerializer

	def get_queryset(self):
		return LeaseAmendment.objects.filter(
			lease__tenant__organization_id__in=self.allowed_organization_ids(),
		).select_related('lease', 'created_by')

	def perform_create(self, serializer):
		lease = serializer.validated_data['lease']
		self.ensure_allowed(lease.organization_id)
		serializer.save(created_by=self.request.user)

	def perform_update(self, serializer):
		lease = serializer.validated_data.get('lease', serializer.instance.lease)
		self.ensure_allowed(lease.organization_id)
		serializer.save()
