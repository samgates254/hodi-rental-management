from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from common.permissions import (
	OrganizationRolePermission,
	user_can_access_organization_resource,
	organization_ids_for_resource,
)

from .models import Building, Property, Unit
from .serializers import BuildingSerializer, PropertySerializer, UnitSerializer


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
		serializer.save()

	def perform_update(self, serializer):
		organization = serializer.validated_data.get(
			'organization',
			serializer.instance.organization,
		)
		self.ensure_allowed(organization.pk)
		serializer.save()


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

	def perform_create(self, serializer):
		building = serializer.validated_data['building']
		self.ensure_allowed(building.property.organization_id)
		serializer.save()

	def perform_update(self, serializer):
		building = serializer.validated_data.get(
			'building',
			serializer.instance.building,
		)
		self.ensure_allowed(building.property.organization_id)
		serializer.save()
