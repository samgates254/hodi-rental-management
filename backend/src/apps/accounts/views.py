import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.organizations.models import Organization
from apps.organizations.models import OrganizationMembership
from apps.tenants.models import Tenant

from .models import AccountProfile
from .serializers import (
	LoginSerializer,
	PasswordResetConfirmSerializer,
	PasswordResetRequestSerializer,
	SignupSerializer,
	TenantOrganizationSerializer,
)
from .services import reset_user_password, send_password_reset_email

logger = logging.getLogger(__name__)


class SignupView(APIView):
	permission_classes = (permissions.AllowAny,)
	authentication_classes = ()
	# ScopedRateThrottle uses process-local LocMem; disable in DEBUG for local DX.
	throttle_classes = () if settings.DEBUG else (ScopedRateThrottle,)
	throttle_scope = 'auth_signup'

	def post(self, request):
		serializer = SignupSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = serializer.save()
		profile = user.account_profile
		token, _created = Token.objects.get_or_create(user=user)
		return Response(
			{
				'detail': 'Account created successfully.',
				'token': token.key,
				'account_type': profile.account_type,
				'organization_id': profile.organization_id,
				'professional_trade': profile.professional_trade,
			},
			status=status.HTTP_201_CREATED,
		)


class OrganizationOptionsView(APIView):
	permission_classes = (permissions.AllowAny,)
	authentication_classes = ()
	throttle_classes = (ScopedRateThrottle,)
	throttle_scope = 'auth_organization_options'

	def get(self, request):
		organizations = Organization.objects.filter(is_active=True).values('id', 'name')
		return Response(list(organizations), status=status.HTTP_200_OK)


class TenantOrganizationView(APIView):
	permission_classes = (permissions.IsAuthenticated,)

	@transaction.atomic
	def post(self, request):
		profile = getattr(request.user, 'account_profile', None)
		if profile is None or profile.account_type != AccountProfile.AccountType.TENANT:
			return Response(
				{'detail': 'Only tenant accounts can select a tenant organization.'},
				status=status.HTTP_403_FORBIDDEN,
			)
		if profile.organization_id is not None:
			return Response(
				{'detail': 'An organization is already assigned to this tenant account.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		serializer = TenantOrganizationSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		organization = serializer.validated_data['organization']
		profile.organization = organization
		profile.save(update_fields=('organization', 'updated_at'))
		Tenant.objects.create(
			user=request.user,
			organization=organization,
			first_name=request.user.first_name,
			last_name=request.user.last_name,
			phone_number=profile.phone_number,
			email=request.user.email,
		)
		return Response(
			{'account_type': profile.account_type, 'organization_id': organization.pk},
			status=status.HTTP_200_OK,
		)


class PasswordResetRequestView(APIView):
	permission_classes = (permissions.AllowAny,)
	authentication_classes = ()
	throttle_classes = (ScopedRateThrottle,)
	throttle_scope = 'auth_password_reset_request'

	def post(self, request):
		serializer = PasswordResetRequestSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = get_user_model().objects.filter(
			email__iexact=serializer.validated_data['email'],
			is_active=True,
		).first()
		if user is not None:
			try:
				send_password_reset_email(user)
			except Exception:
				logger.exception('Unable to send password reset email.')
		return Response(
			{'detail': 'If an active account uses that email, reset instructions will be sent.'},
			status=status.HTTP_202_ACCEPTED,
		)


class PasswordResetConfirmView(APIView):
	permission_classes = (permissions.AllowAny,)
	authentication_classes = ()
	throttle_classes = (ScopedRateThrottle,)
	throttle_scope = 'auth_password_reset_confirm'

	def post(self, request):
		serializer = PasswordResetConfirmSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		try:
			reset = reset_user_password(
				serializer.validated_data['uid'],
				serializer.validated_data['token'],
				serializer.validated_data['password'],
			)
		except DjangoValidationError as error:
			raise ValidationError({'password': error.messages}) from error
		if not reset:
			return Response(
				{'detail': 'This password reset link is invalid or expired.'},
				status=status.HTTP_400_BAD_REQUEST,
			)
		return Response(
			{'detail': 'Your password has been reset. Please log in again.'},
			status=status.HTTP_200_OK,
		)


class LoginView(APIView):
	permission_classes = (permissions.AllowAny,)
	authentication_classes = ()
	throttle_classes = () if settings.DEBUG else (ScopedRateThrottle,)
	throttle_scope = 'auth_login'

	def post(self, request):
		serializer = LoginSerializer(data=request.data, context={'request': request})
		serializer.is_valid(raise_exception=True)
		user = serializer.validated_data['user']
		token, _created = Token.objects.get_or_create(user=user)
		profile = getattr(user, 'account_profile', None)
		response_data = {
			'token': token.key,
			'first_name': user.first_name,
			'last_name': user.last_name,
			'email': user.email,
		}
		if profile is not None:
			response_data.update({
				'account_type': profile.account_type,
				'organization_id': profile.organization_id,
				'professional_trade': profile.professional_trade,
				'phone_number': profile.phone_number,
			})
		memberships = OrganizationMembership.objects.filter(
			user=user,
			is_active=True,
			organization__is_active=True,
		).select_related('organization').order_by('organization__name')
		response_data['memberships'] = [
			{
				'organization_id': membership.organization_id,
				'organization_name': membership.organization.name,
				'role': membership.role,
			}
			for membership in memberships
		]
		return Response(response_data, status=status.HTTP_200_OK)


class MeView(APIView):
	permission_classes = (permissions.IsAuthenticated,)

	def get(self, request):
		user = request.user
		profile = getattr(user, 'account_profile', None)
		memberships = OrganizationMembership.objects.filter(
			user=user,
		).select_related('organization').order_by('organization__name', 'id')
		return Response(
			{
				'id': user.pk,
				'username': user.get_username(),
				'email': user.email,
				'first_name': user.first_name,
				'last_name': user.last_name,
				'account_type': profile.account_type if profile is not None else '',
				'organization_id': profile.organization_id if profile is not None else None,
				'professional_trade': profile.professional_trade if profile is not None else '',
				'phone_number': profile.phone_number if profile is not None else '',
				'memberships': [
					{
						'organization': membership.organization_id,
						'organization_name': membership.organization.name,
						'role': membership.role,
						'is_active': membership.is_active,
					}
					for membership in memberships
				],
			},
			status=status.HTTP_200_OK,
		)


class LogoutView(APIView):
	permission_classes = (permissions.IsAuthenticated,)

	def post(self, request):
		Token.objects.filter(user=request.user).delete()
		return Response(status=status.HTTP_204_NO_CONTENT)