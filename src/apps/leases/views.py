from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.api import organization_ids_for_user

from .models import Lease, LeaseAmendment, RentSchedule
from .serializers import LeaseAmendmentSerializer, LeaseSerializer, RentScheduleSerializer


class LeaseScopedViewSet(viewsets.ModelViewSet):
	permission_classes = (permissions.IsAuthenticated,)

	def allowed_organization_ids(self):
		return organization_ids_for_user(self.request.user)

	def ensure_allowed(self, organization_id):
		if not self.allowed_organization_ids().filter(pk=organization_id).exists():
			raise PermissionDenied('You do not belong to this organization.')


class LeaseViewSet(LeaseScopedViewSet):
	serializer_class = LeaseSerializer

	def get_queryset(self):
		return Lease.objects.filter(
			tenant__organization_id__in=self.allowed_organization_ids(),
		).select_related('tenant', 'unit')

	def perform_create(self, serializer):
		tenant = serializer.validated_data['tenant']
		self.ensure_allowed(tenant.organization_id)
		self.save_and_validate(serializer)

	def perform_update(self, serializer):
		self.save_and_validate(serializer)

	@transaction.atomic
	def save_and_validate(self, serializer):
		instance = serializer.save()
		try:
			instance.full_clean()
		except DjangoValidationError as error:
			raise ValidationError(error.message_dict) from error


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
