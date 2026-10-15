from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated

from application.services.audit import record_audit
from apps.tenants.models import Tenant
from common.permissions import (
    action_for_method,
    organization_ids_for_resource,
    user_can_access_organization_resource,
)

from .serializers import TenantSerializer


SELF_EDITABLE = {'first_name', 'last_name', 'phone_number', 'email'}


class TenantAccess(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        action = action_for_method(request.method)
        if organization_ids_for_resource(user, 'tenants', action).exists():
            return True
        if request.method in ('GET', 'HEAD', 'OPTIONS', 'PATCH', 'PUT'):
            return Tenant.objects.filter(user=user).exists()
        return False


class TenantViewSet(viewsets.ModelViewSet):
    serializer_class = TenantSerializer
    permission_classes = (IsAuthenticated, TenantAccess)
    http_method_names = ('get', 'post', 'put', 'patch', 'head', 'options')

    def get_queryset(self):
        user = self.request.user
        action = 'read' if self.request.method in ('GET', 'HEAD', 'OPTIONS', 'PATCH', 'PUT') else 'write'
        organization_ids = organization_ids_for_resource(user, 'tenants', action if action == 'write' else 'read')
        queryset = Tenant.objects.filter(organization_id__in=organization_ids)
        if self.request.method in ('GET', 'HEAD', 'OPTIONS', 'PATCH', 'PUT'):
            queryset = (queryset | Tenant.objects.filter(user=user)).distinct()
        return queryset

    def perform_create(self, serializer):
        organization = serializer.validated_data['organization']
        if not user_can_access_organization_resource(
            self.request.user,
            organization.pk,
            'tenants',
            'write',
        ):
            raise PermissionDenied('You do not have permission for this organization.')
        tenant = serializer.save()
        record_audit(
            action='tenant.create',
            object_type='Tenant',
            object_id=tenant.pk,
            actor=self.request.user,
            organization=organization,
            metadata={'full_name': tenant.full_name},
            request=self.request,
        )

    def perform_update(self, serializer):
        instance = serializer.instance
        can_write = user_can_access_organization_resource(
            self.request.user,
            instance.organization_id,
            'tenants',
            'write',
        )
        is_self = instance.user_id == self.request.user.id
        if not can_write:
            if not is_self:
                raise PermissionDenied('You do not have permission for this organization.')
            dirty = set(serializer.validated_data) - SELF_EDITABLE
            if dirty:
                raise PermissionDenied('You can only update your own contact details.')
        serializer.save()

    def perform_destroy(self, instance):
        if not user_can_access_organization_resource(
            self.request.user,
            instance.organization_id,
            'tenants',
            'write',
        ):
            raise PermissionDenied('You do not have permission for this organization.')
        instance.delete()
