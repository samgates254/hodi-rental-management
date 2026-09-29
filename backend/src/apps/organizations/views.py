from django.db import transaction
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.api import organization_ids_for_user

from .models import Organization, OrganizationMembership
from .serializers import OrganizationMembershipSerializer, OrganizationSerializer


def require_organization_owner(user, organization):
    if not OrganizationMembership.objects.filter(
        organization=organization,
        user=user,
        role=OrganizationMembership.Role.OWNER,
        is_active=True,
    ).exists():
        raise PermissionDenied('Only an active organization owner can manage this resource.')


def prevent_removing_last_active_owner(membership, role=None, is_active=None, deleting=False):
    if (
        membership.role != OrganizationMembership.Role.OWNER
        or not membership.is_active
    ):
        return

    next_role = membership.role if role is None else role
    next_is_active = membership.is_active if is_active is None else is_active
    if not deleting and next_role == OrganizationMembership.Role.OWNER and next_is_active:
        return

    active_owner_count = OrganizationMembership.objects.filter(
        organization=membership.organization,
        role=OrganizationMembership.Role.OWNER,
        is_active=True,
    ).count()
    if active_owner_count <= 1:
        raise ValidationError('An organization must retain at least one active owner.')


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return Organization.objects.filter(id__in=organization_ids_for_user(self.request.user))

    @transaction.atomic
    def perform_create(self, serializer):
        organization = serializer.save()
        OrganizationMembership.objects.create(
            organization=organization,
            user=self.request.user,
            role=OrganizationMembership.Role.OWNER,
        )

    def perform_update(self, serializer):
        require_organization_owner(self.request.user, serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        require_organization_owner(self.request.user, instance)
        instance.delete()


class OrganizationMembershipViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationMembershipSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return OrganizationMembership.objects.filter(
            organization_id__in=organization_ids_for_user(self.request.user),
        ).select_related('user', 'organization')

    def perform_create(self, serializer):
        organization = serializer.validated_data['organization']
        require_organization_owner(self.request.user, organization)
        serializer.save()

    def perform_update(self, serializer):
        membership = serializer.instance
        require_organization_owner(self.request.user, membership.organization)
        prevent_removing_last_active_owner(
            membership,
            role=serializer.validated_data.get('role'),
            is_active=serializer.validated_data.get('is_active'),
        )
        serializer.save()

    def perform_destroy(self, instance):
        require_organization_owner(self.request.user, instance.organization)
        prevent_removing_last_active_owner(instance, deleting=True)
        instance.delete()
