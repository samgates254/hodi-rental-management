from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from common.api import organization_ids_for_user

from .models import Building, Property, Unit
from .serializers import BuildingSerializer, PropertySerializer, UnitSerializer


class OrganizationScopedViewSet(viewsets.ModelViewSet):
	permission_classes = (permissions.IsAuthenticated,)

	def allowed_organization_ids(self):
		return organization_ids_for_user(self.request.user)

	def ensure_allowed(self, organization_id):
		if not self.allowed_organization_ids().filter(pk=organization_id).exists():
			raise PermissionDenied('You do not belong to this organization.')


class PropertyViewSet(OrganizationScopedViewSet):
	serializer_class = PropertySerializer

	def get_queryset(self):
		return Property.objects.filter(organization_id__in=self.allowed_organization_ids())

	def perform_create(self, serializer):
		organization = serializer.validated_data['organization']
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


class UnitViewSet(OrganizationScopedViewSet):
	serializer_class = UnitSerializer

	def get_queryset(self):
		return Unit.objects.filter(building__property__organization_id__in=self.allowed_organization_ids())

	def perform_create(self, serializer):
		building = serializer.validated_data['building']
		self.ensure_allowed(building.property.organization_id)
		serializer.save()
