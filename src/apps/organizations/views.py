from django.db import transaction
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from common.api import organization_ids_for_user

from .models import Organization, OrganizationMembership
from .serializers import OrganizationMembershipSerializer, OrganizationSerializer


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


class OrganizationMembershipViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationMembershipSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return OrganizationMembership.objects.filter(
            organization_id__in=organization_ids_for_user(self.request.user),
        ).select_related('user', 'organization')

    def perform_create(self, serializer):
        organization = serializer.validated_data['organization']
        if not organization_ids_for_user(self.request.user).filter(pk=organization.pk).exists():
            raise PermissionDenied('You do not belong to this organization.')
        serializer.save()
