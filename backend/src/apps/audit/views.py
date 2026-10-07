from rest_framework import mixins, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.organizations.models import OrganizationMembership

from .models import AuditLog
from .serializers import AuditLogSerializer


AUDIT_ROLES = (
    OrganizationMembership.Role.OWNER,
    OrganizationMembership.Role.PROPERTY_MANAGER,
    OrganizationMembership.Role.ACCOUNTANT,
)


class AuditReadPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return OrganizationMembership.objects.filter(
            user=user,
            is_active=True,
            organization__is_active=True,
            role__in=AUDIT_ROLES,
        ).exists()


class AuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated, AuditReadPermission)
    serializer_class = AuditLogSerializer
    http_method_names = ('get', 'head', 'options')

    def get_queryset(self):
        organization_ids = OrganizationMembership.objects.filter(
            user=self.request.user,
            is_active=True,
            organization__is_active=True,
            role__in=AUDIT_ROLES,
        ).values_list('organization_id', flat=True)
        queryset = AuditLog.objects.filter(organization_id__in=organization_ids)
        organization = self.request.query_params.get('organization')
        if organization:
            try:
                organization = int(organization)
            except ValueError as error:
                raise PermissionDenied('A valid organization is required.') from error
            if organization not in set(organization_ids):
                return AuditLog.objects.none()
            queryset = queryset.filter(organization_id=organization)
        object_type = self.request.query_params.get('object_type')
        if object_type:
            queryset = queryset.filter(object_type=object_type)
        object_id = self.request.query_params.get('object_id')
        if object_id:
            queryset = queryset.filter(object_id=str(object_id))
        return queryset
