from rest_framework import serializers

from apps.properties.models import Unit
from rental_os.algorithms.money import MAX_MONEY_MINOR

from .models import (AgentProfile, AgentUnitAuthorization, CommerceListing, CommerceOrder,
	CommercePhoto, SupplierProfile, Listing, ListingInquiry, ListingPhoto, ViewingRequest)
from .services import is_publicly_available


class SupplierProfileSerializer(serializers.ModelSerializer):
	class Meta:
		model = SupplierProfile
		fields = ('id', 'organization', 'business_name', 'public_email', 'public_phone',
			'show_public_contact', 'categories', 'verification_status', 'is_active', 'created_at')
		read_only_fields = ('verification_status', 'created_at')

	def validate_organization(self, organization):
		from common.permissions import user_can_access_organization_resource
		request = self.context['request']
		if not user_can_access_organization_resource(request.user, organization.pk, 'marketplace', 'write'):
			from rest_framework.exceptions import PermissionDenied
			raise PermissionDenied('You cannot manage suppliers for this organization.')
		return organization


class CommercePhotoSerializer(serializers.ModelSerializer):
	url = serializers.SerializerMethodField()
	class Meta:
		model = CommercePhoto
		fields = ('id', 'url', 'caption', 'position')
	def get_url(self, photo):
		return f'/api/v1/marketplace/commerce/listings/{photo.listing_id}/photos/{photo.pk}/'


class CommerceListingSerializer(serializers.ModelSerializer):
	supplier_name = serializers.CharField(source='supplier.business_name', read_only=True)
	photos = CommercePhotoSerializer(many=True, read_only=True)
	price_minor = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=MAX_MONEY_MINOR)
	class Meta:
		model = CommerceListing
		fields = ('id', 'organization', 'supplier', 'supplier_name', 'kind', 'category', 'title',
			'description', 'specifications', 'price_minor', 'currency', 'price_unit',
			'availability', 'is_published', 'photos', 'created_at')
		read_only_fields = ('created_at',)

	def validate(self, attrs):
		organization = attrs.get('organization', getattr(self.instance, 'organization', None))
		supplier = attrs.get('supplier', getattr(self.instance, 'supplier', None))
		if organization and supplier and supplier.organization_id != organization.pk:
			raise serializers.ValidationError({'supplier': 'Supplier must belong to the listing organization.'})
		if supplier and not supplier.is_active:
			raise serializers.ValidationError({'supplier': 'Listings require an active supplier profile.'})
		price = attrs.get('price_minor', getattr(self.instance, 'price_minor', None))
		if price is not None and price <= 0:
			raise serializers.ValidationError({'price_minor': 'Set a positive price or leave it blank for price on request.'})
		if organization:
			from common.permissions import user_can_access_organization_resource
			if not user_can_access_organization_resource(self.context['request'].user, organization.pk, 'marketplace', 'write'):
				from rest_framework.exceptions import PermissionDenied
				raise PermissionDenied('You cannot manage listings for this organization.')
		return attrs


class CommerceOrderSerializer(serializers.ModelSerializer):
	listing_title = serializers.CharField(source='listing.title', read_only=True)
	supplier_name = serializers.CharField(source='listing.supplier.business_name', read_only=True)
	payment_status = serializers.SerializerMethodField()
	class Meta:
		model = CommerceOrder
		fields = ('id', 'listing', 'listing_title', 'supplier_name', 'quantity', 'request_details',
			'status', 'provider_response', 'payment_status', 'created_at', 'updated_at')
		read_only_fields = ('status', 'provider_response', 'created_at', 'updated_at')
	def get_payment_status(self, order):
		return 'NOT_INTEGRATED'


class ListingPhotoSerializer(serializers.ModelSerializer):
	url = serializers.SerializerMethodField()

	class Meta:
		model = ListingPhoto
		fields = ('id', 'url', 'caption', 'position', 'is_primary')

	def get_url(self, photo):
		scope = self.context.get('photo_scope', 'public')
		if scope == 'manage':
			return f'/api/v1/marketplace/manage/listings/{photo.listing_id}/photos/{photo.pk}/'
		return f'/api/v1/marketplace/listings/{photo.listing_id}/photos/{photo.pk}/'


class PublicListingSerializer(serializers.ModelSerializer):
	photos = serializers.SerializerMethodField()
	property_name = serializers.CharField(source='unit.building.property.name', read_only=True)
	unit_label = serializers.CharField(source='unit.name', read_only=True)
	available = serializers.SerializerMethodField()

	class Meta:
		model = Listing
		fields = (
			'id', 'title', 'description', 'monthly_rent_minor', 'currency',
			'bedrooms', 'bathrooms', 'floor', 'size_sqm', 'furnished', 'amenities',
			'area', 'city', 'country', 'property_name', 'unit_label',
			'available', 'published_at', 'photos',
		)

	def get_available(self, listing):
		return True

	def get_photos(self, listing):
		return ListingPhotoSerializer(listing.photos.all(), many=True, context={'photo_scope': 'public'}).data


class ManagedListingSerializer(serializers.ModelSerializer):
	photos = serializers.SerializerMethodField()
	property_name = serializers.CharField(source='unit.building.property.name', read_only=True)
	unit_label = serializers.CharField(source='unit.name', read_only=True)
	unit_status = serializers.CharField(source='unit.status', read_only=True)
	organization = serializers.IntegerField(source='organization_id', read_only=True)
	responsible_agent = serializers.IntegerField(source='agent_profile_id', read_only=True)
	is_publicly_available = serializers.SerializerMethodField()

	class Meta:
		model = Listing
		fields = (
			'id', 'unit', 'organization', 'title', 'description', 'monthly_rent_minor', 'currency',
			'bedrooms', 'bathrooms', 'floor', 'size_sqm', 'furnished', 'amenities',
			'area', 'city', 'country', 'property_name', 'unit_label', 'unit_status',
			'status', 'responsible_agent', 'is_publicly_available', 'published_at', 'created_at', 'updated_at', 'photos',
		)
		read_only_fields = (
			'id', 'organization', 'property_name', 'unit_label', 'unit_status',
			'status', 'responsible_agent', 'is_publicly_available', 'published_at', 'created_at', 'updated_at', 'photos',
		)

	def get_is_publicly_available(self, listing):
		return is_publicly_available(listing)

	def get_photos(self, listing):
		return ListingPhotoSerializer(listing.photos.all(), many=True, context={'photo_scope': 'manage'}).data


class ListingWriteSerializer(serializers.Serializer):
	unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all())
	title = serializers.CharField(max_length=200)
	description = serializers.CharField(required=False, allow_blank=True, max_length=10000)
	monthly_rent_minor = serializers.IntegerField(min_value=1, max_value=MAX_MONEY_MINOR)
	currency = serializers.CharField(required=False, default='KES', max_length=3)
	bedrooms = serializers.IntegerField(required=False, min_value=0, max_value=30)
	bathrooms = serializers.IntegerField(required=False, min_value=0, max_value=30)
	floor = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=200)
	size_sqm = serializers.IntegerField(required=False, allow_null=True, min_value=1)
	furnished = serializers.BooleanField(required=False)
	amenities = serializers.ListField(child=serializers.CharField(), required=False)
	area = serializers.CharField(required=False, allow_blank=True, max_length=120)
	city = serializers.CharField(required=False, allow_blank=True, max_length=100)
	country = serializers.CharField(required=False, allow_blank=True, max_length=100)


class ListingUpdateSerializer(ListingWriteSerializer):
	title = serializers.CharField(max_length=200, required=False)
	monthly_rent_minor = serializers.IntegerField(min_value=1, max_value=MAX_MONEY_MINOR, required=False)
	unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all(), required=False)


class InquiryWriteSerializer(serializers.Serializer):
	listing = serializers.UUIDField()
	name = serializers.CharField(max_length=120)
	email = serializers.EmailField()
	phone = serializers.CharField(required=False, allow_blank=True, max_length=30)
	message = serializers.CharField(max_length=2000)
	viewing_requested_for = serializers.DateTimeField(required=False)

	def validate_viewing_requested_for(self, value):
		from django.utils import timezone

		if value <= timezone.now():
			raise serializers.ValidationError('Choose a future date and time for the viewing.')
		return value


class InquiryReadSerializer(serializers.ModelSerializer):
	viewing_request = serializers.SerializerMethodField()

	class Meta:
		model = ListingInquiry
		fields = ('id', 'name', 'email', 'phone', 'message', 'status', 'viewing_request', 'created_at')

	def get_viewing_request(self, inquiry):
		try:
			viewing = inquiry.viewing_request
		except ViewingRequest.DoesNotExist:
			return None
		return ViewingRequestReadSerializer(viewing).data


class ViewingRequestReadSerializer(serializers.ModelSerializer):
	class Meta:
		model = ViewingRequest
		fields = ('id', 'requested_for', 'status', 'created_at', 'updated_at')


class AgentProfileSerializer(serializers.ModelSerializer):
	description = serializers.CharField(required=False, allow_blank=True, max_length=2000)

	class Meta:
		model = AgentProfile
		fields = (
			'id', 'display_name', 'public_email', 'public_phone', 'business_name',
			'description', 'service_area', 'verification_status', 'account_status',
			'created_at', 'updated_at',
		)
		read_only_fields = ('id', 'verification_status', 'account_status', 'created_at', 'updated_at')


class AgentUnitAuthorizationCreateSerializer(serializers.Serializer):
	organization = serializers.IntegerField(min_value=1)
	unit = serializers.IntegerField(min_value=1)
	agent_email = serializers.EmailField()
	attest_authority = serializers.BooleanField()
	authority_reference = serializers.CharField(required=False, allow_blank=True, max_length=120)

	def validate_attest_authority(self, value):
		if not value:
			raise serializers.ValidationError('Confirm that you are authorized to grant advertising rights for this unit.')
		return value


class AgentUnitAuthorizationReadSerializer(serializers.ModelSerializer):
	agent_name = serializers.CharField(source='agent.display_name', read_only=True)
	agent_email = serializers.EmailField(source='agent.public_email', read_only=True)
	unit_name = serializers.CharField(source='unit.name', read_only=True)
	property_name = serializers.CharField(source='unit.building.property.name', read_only=True)
	building_name = serializers.CharField(source='unit.building.name', read_only=True)
	organization = serializers.IntegerField(source='unit.building.property.organization_id', read_only=True)

	class Meta:
		model = AgentUnitAuthorization
		fields = (
			'id', 'agent', 'agent_name', 'agent_email', 'unit', 'unit_name', 'building_name',
			'property_name', 'organization', 'status', 'authority_reference', 'granted_at',
			'revoked_at',
		)
		read_only_fields = fields


class AgentInquiryStatusSerializer(serializers.Serializer):
	status = serializers.ChoiceField(choices=ListingInquiry.Status.choices)


class AgentViewingStatusSerializer(serializers.Serializer):
	status = serializers.ChoiceField(choices=ViewingRequest.Status.choices)
