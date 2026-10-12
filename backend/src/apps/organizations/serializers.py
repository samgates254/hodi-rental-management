from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import AccountProfile

from .models import Organization, OrganizationMembership
from .roles import STAFF_ROLE_CHOICES, ensure_role_profile

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ('id', 'name', 'slug', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            self.fields['organization'].read_only = True

    class Meta:
        model = OrganizationMembership
        fields = ('id', 'organization', 'user', 'role', 'is_active', 'created_at')
        read_only_fields = ('id', 'created_at')


class OrganizationStaffSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    phone_number = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationMembership
        fields = (
            'id', 'organization', 'user', 'username', 'first_name', 'last_name',
            'email', 'phone_number', 'role', 'is_active', 'created_at',
        )
        read_only_fields = fields

    def get_phone_number(self, membership):
        profile = getattr(membership.user, 'account_profile', None)
        return profile.phone_number if profile else ''


class OrganizationStaffCreateSerializer(serializers.Serializer):
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.filter(is_active=True),
    )
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=30, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=STAFF_ROLE_CHOICES)
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
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': 'The passwords do not match.',
            })
        user = User(
            username=attrs['username'],
            email=attrs['email'],
            first_name=attrs['first_name'],
            last_name=attrs['last_name'],
        )
        try:
            password_validation.validate_password(attrs['password'], user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({'password': error.messages}) from error
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        organization = validated_data.pop('organization')
        role = validated_data.pop('role')
        phone_number = validated_data.pop('phone_number', '')
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User.objects.create_user(
            is_active=True,
            password=password,
            **validated_data,
        )
        AccountProfile.objects.create(
            user=user,
            account_type=AccountProfile.AccountType.UNSPECIFIED,
            phone_number=phone_number,
        )
        membership = OrganizationMembership.objects.create(
            organization=organization,
            user=user,
            role=role,
        )
        ensure_role_profile(user, role)
        return membership
