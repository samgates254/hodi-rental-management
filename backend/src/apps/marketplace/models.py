import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.properties.models import Unit


class Listing(models.Model):
	class Status(models.TextChoices):
		DRAFT = 'DRAFT', 'Draft'
		PUBLISHED = 'PUBLISHED', 'Published'

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	unit = models.OneToOneField(
		Unit,
		on_delete=models.PROTECT,
		related_name='marketplace_listing',
	)
	title = models.CharField(max_length=200)
	description = models.TextField(blank=True)
	monthly_rent_minor = models.PositiveBigIntegerField()
	currency = models.CharField(max_length=3, default='KES')
	bedrooms = models.PositiveSmallIntegerField(default=0)
	bathrooms = models.PositiveSmallIntegerField(default=0)
	floor = models.PositiveSmallIntegerField(null=True, blank=True)
	size_sqm = models.PositiveIntegerField(null=True, blank=True)
	furnished = models.BooleanField(default=False)
	amenities = models.JSONField(default=list, blank=True)
	area = models.CharField(max_length=120, blank=True)
	city = models.CharField(max_length=100)
	country = models.CharField(max_length=100, default='Kenya')
	status = models.CharField(
		max_length=20,
		choices=Status.choices,
		default=Status.DRAFT,
	)
	published_at = models.DateTimeField(null=True, blank=True)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='marketplace_listings',
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('-created_at',)
		indexes = [
			models.Index(fields=('status', '-created_at'), name='mkt_listing_status_created_idx'),
			models.Index(fields=('city', 'status'), name='mkt_listing_city_status_idx'),
			models.Index(fields=('monthly_rent_minor',), name='mkt_listing_rent_idx'),
			models.Index(fields=('bedrooms', 'status'), name='mkt_listing_beds_status_idx'),
		]
		constraints = [
			models.CheckConstraint(
				check=Q(monthly_rent_minor__gt=0),
				name='mkt_listing_rent_positive',
			),
		]

	@property
	def organization_id(self):
		return self.unit.organization_id

	def __str__(self):
		return self.title


class ListingPhoto(models.Model):
	listing = models.ForeignKey(
		Listing,
		on_delete=models.CASCADE,
		related_name='photos',
	)
	image = models.FileField(upload_to='marketplace/listings/%Y/%m/')
	file_name = models.CharField(max_length=255)
	content_type = models.CharField(max_length=100)
	caption = models.CharField(max_length=200, blank=True)
	position = models.PositiveSmallIntegerField(default=0)
	is_primary = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('position', 'pk')
		constraints = [
			models.UniqueConstraint(
				fields=('listing',),
				condition=Q(is_primary=True),
				name='unique_primary_mkt_photo',
			),
		]

	def __str__(self):
		return self.file_name


class ListingInquiry(models.Model):
	listing = models.ForeignKey(
		Listing,
		on_delete=models.CASCADE,
		related_name='inquiries',
	)
	name = models.CharField(max_length=120)
	email = models.EmailField()
	phone = models.CharField(max_length=30, blank=True)
	message = models.TextField()
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('-created_at', 'pk')
		indexes = [
			models.Index(fields=('listing', '-created_at'), name='mkt_inquiry_created_idx'),
		]

	def __str__(self):
		return f'{self.name} → {self.listing_id}'
