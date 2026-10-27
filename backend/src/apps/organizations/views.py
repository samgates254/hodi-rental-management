from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from application.services.audit import record_audit
from common.api import organization_ids_for_user

from .models import AccountantInvitation, Organization, OrganizationMembership
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

    staff_roles = (*STAFF_ROLE_VALUES, OrganizationMembership.Role.ACCOUNTANT)

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
        if serializer.validated_data.get('role') == OrganizationMembership.Role.ACCOUNTANT:
            raise ValidationError({'role': 'Accountant access requires an explicit invitation and acceptance.'})
        membership = serializer.save()
        return Response(
            OrganizationStaffSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )


class AccountantInvitationView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        from django.db.models import Q
        rows = AccountantInvitation.objects.filter(Q(invited_user=request.user) | Q(invited_by=request.user)).select_related('organization','invited_user')
        return Response([{'id': row.pk, 'organization_id': row.organization_id,
            'organization_name': row.organization.name if row.invited_user_id == request.user.pk else row.organization.name,
            'email': row.invited_user.email, 'status': row.status, 'expires_at': row.expires_at,
            'can_accept': row.invited_user_id == request.user.pk,
            'created_at': row.created_at} for row in rows])

    @transaction.atomic
    def post(self, request):
        from rest_framework.exceptions import NotFound
        organization_id = request.data.get('organization')
        email = (request.data.get('email') or '').strip()
        if not email: raise ValidationError({'email': 'An accountant email is required.'})
        try: organization = Organization.objects.get(pk=organization_id, is_active=True)
        except (Organization.DoesNotExist, ValueError, TypeError) as error: raise NotFound('Organization not found.') from error
        require_organization_owner(request.user, organization)
        try: invitee = get_user_model().objects.get(email__iexact=email, is_active=True)
        except get_user_model().DoesNotExist as error: raise ValidationError({'email': 'An existing account is required for an invitation.'}) from error
        if invitee.pk == request.user.pk: raise ValidationError({'email': 'You cannot invite your own account.'})
        membership = OrganizationMembership.objects.filter(organization=organization,user=invitee).first()
        if membership and membership.is_active:
            raise ValidationError({'email': 'This user already has active access to the organization.'})
        pending = AccountantInvitation.objects.filter(organization=organization,invited_user=invitee,status='PENDING').first()
        if pending and pending.expires_at > timezone.now(): return Response({'id': pending.pk, 'status': pending.status}, status=status.HTTP_200_OK)
        if pending: pending.status='EXPIRED'; pending.save(update_fields=('status',))
        invitation = AccountantInvitation.objects.create(organization=organization, invited_user=invitee,
            invited_by=request.user, expires_at=timezone.now()+timedelta(days=7))
        record_audit(action='accountant.invitation.create', object_type='AccountantInvitation', object_id=invitation.pk,
            actor=request.user, organization=organization, metadata={'invited_user_id': invitee.pk}, request=request)
        return Response({'id': invitation.pk, 'status': invitation.status, 'expires_at': invitation.expires_at}, status=status.HTTP_201_CREATED)


class AccountantInvitationActionView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, invitation_id, action):
        from rest_framework.exceptions import NotFound
        try: invite = AccountantInvitation.objects.select_for_update().select_related('organization','invited_user').get(pk=invitation_id)
        except AccountantInvitation.DoesNotExist as error: raise NotFound('Invitation not found.') from error
        if action in ('accept','decline'):
            if invite.invited_user_id != request.user.pk: raise NotFound('Invitation not found.')
            if invite.status == 'ACCEPTED' and action == 'accept': return Response({'status':'ACCEPTED'})
            if invite.status != 'PENDING': raise ValidationError({'status': 'This invitation is no longer available.'})
            if invite.expires_at <= timezone.now():
                invite.status='EXPIRED'; invite.save(update_fields=('status',)); raise ValidationError({'status':'This invitation has expired.'})
            if action == 'accept':
                membership, _ = OrganizationMembership.objects.get_or_create(organization=invite.organization,user=request.user,
                    defaults={'role': OrganizationMembership.Role.ACCOUNTANT, 'is_active': True})
                if membership.role != OrganizationMembership.Role.ACCOUNTANT:
                    raise ValidationError({'membership': 'This account already has a different organisation role.'})
                if not membership.is_active: membership.is_active=True; membership.save(update_fields=('is_active',))
                invite.status='ACCEPTED'; invite.accepted_at=timezone.now()
            else: invite.status='DECLINED'
            invite.save(update_fields=('status','accepted_at'))
        elif action == 'revoke':
            require_organization_owner(request.user, invite.organization)
            if invite.status not in ('PENDING','ACCEPTED'): raise ValidationError({'status':'This invitation cannot be revoked.'})
            invite.status='REVOKED'; invite.revoked_at=timezone.now(); invite.revoked_by=request.user
            invite.save(update_fields=('status','revoked_at','revoked_by'))
            OrganizationMembership.objects.filter(organization=invite.organization,user=invite.invited_user,
                role=OrganizationMembership.Role.ACCOUNTANT,is_active=True).update(is_active=False)
        else: raise ValidationError({'action':'Use accept, decline, or revoke.'})
        record_audit(action=f'accountant.invitation.{action}', object_type='AccountantInvitation', object_id=invite.pk,
            actor=request.user, organization=invite.organization, metadata={'status': invite.status}, request=request)
        return Response({'id':invite.pk,'status':invite.status})


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
        organization_id = serializer.validated_data['organization'].pk
        organization = Organization.objects.select_for_update(of=('self',)).get(pk=organization_id)
        require_organization_owner(self.request.user, organization)
        if serializer.validated_data.get('role') == OrganizationMembership.Role.ACCOUNTANT:
            raise ValidationError({'role': 'Accountant access must be granted through an accepted invitation.'})
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
        membership_id = serializer.instance.pk
        organization_id = serializer.instance.organization_id
        organization = Organization.objects.select_for_update(of=('self',)).get(pk=organization_id)
        membership = OrganizationMembership.objects.select_for_update(of=('self',)).select_related(
            'user', 'organization',
        ).get(pk=membership_id, organization=organization)
        serializer.instance = membership
        require_organization_owner(self.request.user, organization)
        if membership.role == OrganizationMembership.Role.ACCOUNTANT or serializer.validated_data.get('role') == OrganizationMembership.Role.ACCOUNTANT:
            raise ValidationError({'role': 'Accountant access changes must use the invitation workflow.'})
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

    @transaction.atomic
    def perform_destroy(self, instance):
        organization = Organization.objects.select_for_update(of=('self',)).get(pk=instance.organization_id)
        instance = OrganizationMembership.objects.select_for_update(of=('self',)).select_related(
            'user', 'organization',
        ).get(pk=instance.pk, organization=organization)
        require_organization_owner(self.request.user, organization)
        if instance.role == OrganizationMembership.Role.ACCOUNTANT:
            raise ValidationError('Revoke accountant access through its invitation so the change remains auditable.')
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
