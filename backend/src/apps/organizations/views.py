from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from application.services.audit import record_audit
from common.api import organization_ids_for_user

from .models import Organization, OrganizationMembership
from .roles import STAFF_ROLE_VALUES, ensure_role_profile
from .serializers import (
    OrganizationMembershipSerializer,
    OrganizationSerializer,
    OrganizationStaffCreateSerializer,
    OrganizationStaffSerializer,
)


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


class OrganizationStaffView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    staff_roles = STAFF_ROLE_VALUES

    def get_organization(self, organization_id):
        if not organization_id:
            raise ValidationError({'organization': 'An organization ID is required.'})
        try:
            return Organization.objects.get(pk=organization_id, is_active=True)
        except (Organization.DoesNotExist, ValueError) as error:
            raise ValidationError({'organization': 'An active organization is required.'}) from error

    def get(self, request):
        organization = self.get_organization(request.query_params.get('organization'))
        require_organization_owner(request.user, organization)
        memberships = OrganizationMembership.objects.filter(
            organization=organization,
            role__in=self.staff_roles,
        ).select_related('user', 'organization', 'user__account_profile').order_by('user__first_name', 'user__last_name', 'user__username')
        return Response(OrganizationStaffSerializer(memberships, many=True).data)

    def post(self, request):
        organization = self.get_organization(request.data.get('organization'))
        require_organization_owner(request.user, organization)
        serializer = OrganizationStaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        return Response(
            OrganizationStaffSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )


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
        from apps.billing.models import Invoice, Payment, RentPayment
        from apps.properties.models import Property

        if Property.objects.filter(organization=instance).exists():
            raise ValidationError('Organization cannot be deleted while properties exist.')
        if (
            Invoice.objects.filter(organization=instance).exists()
            or Payment.objects.filter(organization=instance).exists()
            or RentPayment.objects.filter(lease__tenant__organization=instance).exists()
        ):
            raise ValidationError('Organization cannot be deleted while financial records exist.')
        from apps.subscriptions.models import OrganizationSubscription

        subscription = OrganizationSubscription.objects.filter(organization=instance).first()
        if subscription and subscription.invoices.exists():
            raise ValidationError('Organization cannot be deleted while Hodi subscription billing history exists.')
        if subscription:
            subscription.delete()
        instance.delete()


class OrganizationMembershipViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationMembershipSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return OrganizationMembership.objects.filter(
            organization_id__in=organization_ids_for_user(self.request.user),
        ).select_related('user', 'organization')

    @transaction.atomic
    def perform_create(self, serializer):
        organization = serializer.validated_data['organization']
        require_organization_owner(self.request.user, organization)
        membership = serializer.save()
        ensure_role_profile(membership.user, membership.role)
        record_audit(
            action='membership.create',
            object_type='OrganizationMembership',
            object_id=membership.pk,
            actor=self.request.user,
            organization=organization,
            metadata={
                'user_id': membership.user_id,
                'role': membership.role,
                'is_active': membership.is_active,
            },
            request=self.request,
        )

    @transaction.atomic
    def perform_update(self, serializer):
        membership = serializer.instance
        require_organization_owner(self.request.user, membership.organization)
        prevent_removing_last_active_owner(
            membership,
            role=serializer.validated_data.get('role'),
            is_active=serializer.validated_data.get('is_active'),
        )
        membership = serializer.save()
        ensure_role_profile(membership.user, membership.role)
        record_audit(
            action='membership.update',
            object_type='OrganizationMembership',
            object_id=membership.pk,
            actor=self.request.user,
            organization=membership.organization,
            metadata={
                'user_id': membership.user_id,
                'role': membership.role,
                'is_active': membership.is_active,
            },
            request=self.request,
        )

    def perform_destroy(self, instance):
        require_organization_owner(self.request.user, instance.organization)
        prevent_removing_last_active_owner(instance, deleting=True)
        record_audit(
            action='membership.delete',
            object_type='OrganizationMembership',
            object_id=instance.pk,
            actor=self.request.user,
            organization=instance.organization,
            metadata={'user_id': instance.user_id, 'role': instance.role},
            request=self.request,
        )
        instance.delete()
