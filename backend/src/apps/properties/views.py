from django.db import transaction
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError

from application.services.audit import record_audit
from common.permissions import (
	OrganizationRolePermission,
	user_can_access_organization_resource,
	organization_ids_for_resource,
)

from .models import Building, Property, Unit
from .serializers import BuildingSerializer, PropertySerializer, UnitSerializer
from apps.subscriptions.services import ensure_unit_capacity


class OrganizationScopedViewSet(viewsets.ModelViewSet):
	permission_classes = (OrganizationRolePermission,)
	organization_resource = 'properties'

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


class PropertyViewSet(OrganizationScopedViewSet):
	serializer_class = PropertySerializer

	def get_queryset(self):
		return Property.objects.filter(organization_id__in=self.allowed_organization_ids())

	def perform_create(self, serializer):
		organization = serializer.validated_data['organization']
		self.ensure_allowed(organization.pk)
		property_record = serializer.save()
		record_audit(
			action='property.create',
			object_type='Property',
			object_id=property_record.pk,
			actor=self.request.user,
			organization=organization,
			metadata={'name': property_record.name},
			request=self.request,
		)

	def perform_update(self, serializer):
		organization = serializer.validated_data.get(
			'organization',
			serializer.instance.organization,
		)
		self.ensure_allowed(organization.pk)
		property_record = serializer.save()
		record_audit(
			action='property.update',
			object_type='Property',
			object_id=property_record.pk,
			actor=self.request.user,
			organization=property_record.organization,
			metadata={'name': property_record.name},
			request=self.request,
		)


class BuildingViewSet(OrganizationScopedViewSet):
	serializer_class = BuildingSerializer

	def get_queryset(self):
		return Building.objects.filter(property__organization_id__in=self.allowed_organization_ids())

	def perform_create(self, serializer):
		property_record = serializer.validated_data['property']
		self.ensure_allowed(property_record.organization_id)
		serializer.save()

	def perform_update(self, serializer):
		property_record = serializer.validated_data.get(
			'property',
			serializer.instance.property,
		)
		self.ensure_allowed(property_record.organization_id)
		serializer.save()


class UnitViewSet(OrganizationScopedViewSet):
	serializer_class = UnitSerializer

	def get_queryset(self):
		return Unit.objects.filter(building__property__organization_id__in=self.allowed_organization_ids())

	@transaction.atomic
	def perform_create(self, serializer):
		building = serializer.validated_data['building']
		self.ensure_allowed(building.property.organization_id)
		ensure_unit_capacity(
			building.property.organization_id,
			counts_as_rentable=serializer.validated_data.get('status', Unit.Status.AVAILABLE) != Unit.Status.INACTIVE,
		)
		unit = serializer.save()
		record_audit(
			action='unit.create',
			object_type='Unit',
			object_id=unit.pk,
			actor=self.request.user,
			organization=building.property.organization,
			metadata={'name': unit.name},
			request=self.request,
		)

	@transaction.atomic
	def perform_update(self, serializer):
		building = serializer.validated_data.get(
			'building',
			serializer.instance.building,
		)
		self.ensure_allowed(building.property.organization_id)
		unit = serializer.instance
		if building.pk != unit.building_id and unit.leases.exists():
			raise ValidationError({
				'building': 'A unit with lease history cannot be moved to another building.'
			})
		new_status = serializer.validated_data.get('status', serializer.instance.status)
		if (
			new_status in (Unit.Status.AVAILABLE, Unit.Status.INACTIVE)
			and unit.leases.filter(status='ACTIVE').exists()
		):
			raise ValidationError({
				'status': 'A unit with an active lease cannot be made available or inactive.'
			})
		existing_organization_id = (
			serializer.instance.building.property.organization_id
		)
		ensure_unit_capacity(
			building.property.organization_id,
			counts_as_rentable=new_status != Unit.Status.INACTIVE,
			existing_unit_id=serializer.instance.pk if building.property.organization_id == existing_organization_id else None,
		)
		unit = serializer.save()
		record_audit(
			action='unit.update',
			object_type='Unit',
			object_id=unit.pk,
			actor=self.request.user,
			organization=unit.building.property.organization,
			metadata={'name': unit.name, 'status': unit.status},
			request=self.request,
		)
