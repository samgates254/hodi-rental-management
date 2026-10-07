from rest_framework import serializers

from apps.properties.models import Unit

from .models import Listing, ListingInquiry, ListingPhoto
from .services import is_publicly_available


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
	is_publicly_available = serializers.SerializerMethodField()

	class Meta:
		model = Listing
		fields = (
			'id', 'unit', 'organization', 'title', 'description', 'monthly_rent_minor', 'currency',
			'bedrooms', 'bathrooms', 'floor', 'size_sqm', 'furnished', 'amenities',
			'area', 'city', 'country', 'property_name', 'unit_label', 'unit_status',
			'status', 'is_publicly_available', 'published_at', 'created_at', 'updated_at', 'photos',
		)
		read_only_fields = (
			'id', 'organization', 'property_name', 'unit_label', 'unit_status',
			'status', 'is_publicly_available', 'published_at', 'created_at', 'updated_at', 'photos',
		)

	def get_is_publicly_available(self, listing):
		return is_publicly_available(listing)

	def get_photos(self, listing):
		return ListingPhotoSerializer(listing.photos.all(), many=True, context={'photo_scope': 'manage'}).data


class ListingWriteSerializer(serializers.Serializer):
	unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all())
	title = serializers.CharField(max_length=200)
	description = serializers.CharField(required=False, allow_blank=True)
	monthly_rent_minor = serializers.IntegerField(min_value=1)
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
	monthly_rent_minor = serializers.IntegerField(min_value=1, required=False)
	unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all(), required=False)


class InquiryWriteSerializer(serializers.Serializer):
	listing = serializers.UUIDField()
	name = serializers.CharField(max_length=120)
	email = serializers.EmailField()
	phone = serializers.CharField(required=False, allow_blank=True, max_length=30)
	message = serializers.CharField(max_length=2000)


class InquiryReadSerializer(serializers.ModelSerializer):
	class Meta:
		model = ListingInquiry
		fields = ('id', 'name', 'email', 'phone', 'message', 'created_at')
