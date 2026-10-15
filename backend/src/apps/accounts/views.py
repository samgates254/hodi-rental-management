import hashlib
import hmac
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.cache import cache
from django.db import transaction
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.id_token import verify_oauth2_token
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from knox.models import AuthToken

from apps.organizations.models import Organization
from apps.organizations.models import OrganizationMembership
from apps.tenants.models import Tenant

from .models import AccountProfile
from .serializers import (
	EmailVerificationConfirmSerializer,
	EmailVerificationRequestSerializer,
	LoginSerializer,
	PasswordResetConfirmSerializer,
	PasswordResetRequestSerializer,
	SignupSerializer,
	TenantOrganizationSerializer,
)
from .services import (
	reset_user_password,
	send_password_reset_email,
	send_verification_email,
	verify_email_token,
)

logger = logging.getLogger(__name__)


def _auth_response_data(user):
	profile = getattr(user, 'account_profile', None)
	_instance, token = AuthToken.objects.create(user=user)
	response_data = {
		'token': token,
		'is_staff': user.is_staff,
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
	agent_profile = getattr(user, 'agent_profile', None)
	if agent_profile is not None:
		response_data['agent_verification_status'] = agent_profile.verification_status
		response_data['agent_account_status'] = agent_profile.account_status
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
	return response_data


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
		verification_required = profile.account_type == AccountProfile.AccountType.PROPERTY_AGENT
		token = None
		if verification_required:
			try:
				send_verification_email(user)
			except Exception:
				# Keep the response generic and never log token or email content.
				logger.error('Unable to send agent email-verification message user_id=%s', user.pk)
		else:
			_instance, token = AuthToken.objects.create(user=user)
		return Response(
			{
				'detail': (
					'Account created. Check your email for a verification link.'
					if verification_required else 'Account created successfully.'
				),
				'token': token if token else None,
				'email_verification_required': verification_required,
				'account_type': profile.account_type,
				'organization_id': profile.organization_id,
				'professional_trade': profile.professional_trade,
				'agent_verification_status': (
					user.agent_profile.verification_status
					if profile.account_type == AccountProfile.AccountType.PROPERTY_AGENT
					else None
				),
			},
			status=status.HTTP_201_CREATED,
		)


def _email_verification_resend_allowed(email):
	key_digest = hmac.new(
		settings.SECRET_KEY.encode('utf-8'),
		email.casefold().encode('utf-8'),
		hashlib.sha256,
	).hexdigest()
	key = f'account-email-verification:{key_digest}'
	try:
		if cache.add(key, 1, timeout=3600):
			return True
		return cache.incr(key) <= 3
	except Exception:
		# Email delivery is disabled if its abuse-control store is unavailable.
		logger.error('Email-verification rate limiter is unavailable.')
		return False


class EmailVerificationRequestView(APIView):
	permission_classes = (permissions.AllowAny,)
	authentication_classes = ()
	throttle_classes = (ScopedRateThrottle,)
	throttle_scope = 'auth_email_verification_request'

	def post(self, request):
		serializer = EmailVerificationRequestSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		email = serializer.validated_data['email']
		response = {
			'detail': 'If an eligible account uses that email, verification instructions will be sent.',
		}
		if not _email_verification_resend_allowed(email):
			return Response(response, status=status.HTTP_202_ACCEPTED)

		user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
		profile = getattr(user, 'account_profile', None) if user is not None else None
		if (
			profile is not None
			and profile.account_type == AccountProfile.AccountType.PROPERTY_AGENT
			and profile.email_verified_at is None
		):
			try:
				send_verification_email(user)
			except Exception:
				logger.error('Unable to send agent email-verification message user_id=%s', user.pk)
		return Response(response, status=status.HTTP_202_ACCEPTED)


class EmailVerificationConfirmView(APIView):
	permission_classes = (permissions.AllowAny,)
	authentication_classes = ()
	throttle_classes = (ScopedRateThrottle,)
	throttle_scope = 'auth_email_verification_confirm'

	def post(self, request):
		serializer = EmailVerificationConfirmSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = verify_email_token(serializer.validated_data['token'])
		if user is None:
			return Response(
				{'detail': 'This verification link is invalid, expired, or already used.'},
				status=status.HTTP_400_BAD_REQUEST,
			)
		_instance, token = AuthToken.objects.create(user=user)
		profile = user.account_profile
		agent_profile = getattr(user, 'agent_profile', None)
		return Response(
			{
				'detail': 'Email verified successfully.',
				'token': token,
				'account_type': profile.account_type,
				'first_name': user.first_name,
				'last_name': user.last_name,
				'email': user.email,
				'phone_number': profile.phone_number,
				'agent_verification_status': (
					agent_profile.verification_status if agent_profile is not None else None
				),
				'agent_account_status': (
					agent_profile.account_status if agent_profile is not None else None
				),
			},
			status=status.HTTP_200_OK,
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
				logger.error('Unable to send password reset email user_id=%s', user.pk)
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
        profile = getattr(user, 'account_profile', None)

        if (
            profile is not None
            and profile.account_type == AccountProfile.AccountType.PROPERTY_AGENT
            and profile.email_verified_at is None
        ):
            return Response(
                {'detail': 'Verify your email address before signing in.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(_auth_response_data(user), status=status.HTTP_200_OK)


class GoogleLoginView(APIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()
    throttle_classes = () if settings.DEBUG else (ScopedRateThrottle,)
    throttle_scope = 'auth_login'

    def post(self, request):
        client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        if not client_id:
            return Response(
                {'detail': 'Google sign-in is not configured.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        credential = request.data.get('credential')
        if not isinstance(credential, str) or not credential:
            return Response(
                {'credential': ['This field is required.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            claims = verify_oauth2_token(
                credential,
                GoogleRequest(),
                audience=client_id,
            )
        except (GoogleAuthError, ValueError):
            return Response(
                {'detail': 'Unable to sign in with this Google account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = claims.get('email')
        if not claims.get('email_verified') or not isinstance(email, str) or not email.strip():
            return Response(
                {'detail': 'Unable to sign in with this Google account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = get_user_model().objects.filter(
            email__iexact=email.strip(),
            is_active=True,
        ).first()

        if user is None:
            return Response(
                {'detail': 'Unable to sign in with this Google account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(_auth_response_data(user), status=status.HTTP_200_OK)


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
				'email_verified': profile.email_verified_at is not None if profile is not None else False,
				'agent_verification_status': getattr(
					getattr(user, 'agent_profile', None), 'verification_status', None,
				),
				'agent_account_status': getattr(
					getattr(user, 'agent_profile', None), 'account_status', None,
				),
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
		if hasattr(request, '_auth') and request._auth is not None:
			# With Knox, request._auth is the AuthToken instance
			if hasattr(request._auth, 'delete'):
				request._auth.delete()
		return Response(status=status.HTTP_204_NO_CONTENT)
