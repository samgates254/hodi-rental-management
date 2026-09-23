from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from common.api import organization_ids_for_user

from .models import Tenant
from .serializers import TenantSerializer


class TenantViewSet(viewsets.ModelViewSet):
	serializer_class = TenantSerializer
	permission_classes = (permissions.IsAuthenticated,)

	def get_queryset(self):
		return Tenant.objects.filter(
			organization_id__in=organization_ids_for_user(self.request.user),
		)

	def perform_create(self, serializer):
		organization = serializer.validated_data['organization']
		if not organization_ids_for_user(self.request.user).filter(pk=organization.pk).exists():
			raise PermissionDenied('You do not belong to this organization.')
		serializer.save()
