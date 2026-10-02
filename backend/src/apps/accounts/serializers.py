from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework.authtoken.models import Token

from .models import AccountProfile
from apps.organizations.models import Organization
from apps.organizations.models import OrganizationMembership
from apps.tenants.models import Tenant

User = get_user_model()


class SignupSerializer(serializers.Serializer):
	account_type = serializers.ChoiceField(choices=tuple(
		choice
		for choice in AccountProfile.AccountType.choices
		if choice[0] != AccountProfile.AccountType.UNSPECIFIED
	))
	username = serializers.CharField(max_length=150)
	email = serializers.EmailField()
	first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
	last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
	phone_number = serializers.CharField(max_length=30, required=False, allow_blank=True)
	organization_id = serializers.PrimaryKeyRelatedField(
		source='organization',
		queryset=Organization.objects.filter(is_active=True),
		required=False,
		allow_null=True,
	)
	organization_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
	professional_trade = serializers.ChoiceField(
		choices=AccountProfile.ProfessionalTrade.choices,
		required=False,
	)
	password = serializers.CharField(write_only=True, trim_whitespace=False)
	password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

	def validate_username(self, username):
		if User.objects.filter(username__iexact=username).exists():
			raise serializers.ValidationError('A user with this username already exists.')
		return username

	def validate_email(self, email):
		email = email.strip().lower()
		if User.objects.filter(email__iexact=email).exists():
			raise serializers.ValidationError('A user with this email already exists.')
		return email

	def validate(self, attrs):
		account_type = attrs['account_type']
		organization = attrs.get('organization')
		organization_name = attrs.get('organization_name', '').strip()
		professional_trade = attrs.get('professional_trade', '')

		if account_type == AccountProfile.AccountType.OWNER:
			if not organization_name:
				raise serializers.ValidationError({
					'organization_name': 'Organization owners must provide an organization name.',
				})
			if organization is not None or professional_trade:
				raise serializers.ValidationError(
					'Owners cannot select an existing organization or repair trade.',
				)
		elif account_type == AccountProfile.AccountType.TENANT:
			if organization_name or professional_trade:
				raise serializers.ValidationError(
					'Tenants may select an existing organization or leave it unset for later.',
				)
		elif account_type == AccountProfile.AccountType.SERVICE_PROFESSIONAL:
			if not professional_trade:
				raise serializers.ValidationError({
					'professional_trade': 'Select your repair trade.',
				})
			if organization is not None or organization_name:
				raise serializers.ValidationError(
					'Service professionals do not select an organization during signup.',
				)

		if attrs['password'] != attrs['password_confirm']:
			raise serializers.ValidationError({
				'password_confirm': 'The passwords do not match.',
			})

		user = User(
			username=attrs['username'],
			email=attrs['email'],
			first_name=attrs.get('first_name', ''),
			last_name=attrs.get('last_name', ''),
		)
		try:
			password_validation.validate_password(attrs['password'], user)
		except DjangoValidationError as error:
			raise serializers.ValidationError({'password': error.messages}) from error
		return attrs

	@transaction.atomic
	def create(self, validated_data):
		validated_data.pop('password_confirm')
		phone_number = validated_data.pop('phone_number', '')
		password = validated_data.pop('password')
		account_type = validated_data.pop('account_type')
		organization = validated_data.pop('organization', None)
		organization_name = validated_data.pop('organization_name', '').strip()
		professional_trade = validated_data.pop('professional_trade', '')
		user = User.objects.create_user(is_active=True, password=password, **validated_data)
		profile = AccountProfile.objects.create(
			user=user,
			account_type=account_type,
			organization=organization,
			organization_name=organization_name,
			professional_trade=professional_trade,
			phone_number=phone_number,
		)
		if account_type == AccountProfile.AccountType.OWNER:
			organization = Organization.objects.create(name=organization_name)
			OrganizationMembership.objects.create(
				organization=organization,
				user=user,
				role=OrganizationMembership.Role.OWNER,
			)
			profile.organization = organization
			profile.organization_name = ''
			profile.save(update_fields=('organization', 'organization_name', 'updated_at'))
		elif account_type == AccountProfile.AccountType.TENANT and organization is not None:
			Tenant.objects.create(
				user=user,
				organization=organization,
				first_name=user.first_name,
				last_name=user.last_name,
				phone_number=phone_number,
				email=user.email,
			)
		Token.objects.create(user=user)
		return user


class LoginSerializer(serializers.Serializer):
	username = serializers.CharField(label='Username')
	password = serializers.CharField(
		label='Password',
		style={'input_type': 'password'},
		trim_whitespace=False,
	)

	def validate(self, attrs):
		from django.contrib.auth import authenticate

		request = self.context.get('request')
		user = authenticate(
			request=request,
			username=attrs.get('username'),
			password=attrs.get('password'),
		)
		if not user:
			raise serializers.ValidationError(
				'Unable to log in with provided credentials.',
				code='authorization',
			)

		attrs['user'] = user
		return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
	email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
	uid = serializers.CharField()
	token = serializers.CharField(trim_whitespace=True)
	password = serializers.CharField(write_only=True, trim_whitespace=False)
	password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

	def validate(self, attrs):
		if attrs['password'] != attrs['password_confirm']:
			raise serializers.ValidationError({
				'password_confirm': 'The passwords do not match.',
			})
		return attrs

class TenantOrganizationSerializer(serializers.Serializer):
	organization_id = serializers.PrimaryKeyRelatedField(
		source='organization',
		queryset=Organization.objects.filter(is_active=True),
	)