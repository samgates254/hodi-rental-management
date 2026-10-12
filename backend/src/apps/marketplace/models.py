import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.organizations.models import Organization
from apps.properties.models import Unit
from apps.tenants.models import Tenant


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


class SupplierProfile(models.Model):
	class VerificationStatus(models.TextChoices):
		UNVERIFIED = 'UNVERIFIED', 'Not verified'

	organization = models.ForeignKey(
		Organization, on_delete=models.CASCADE, related_name='supplier_profiles',
	)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='supplier_profiles_created',
	)
	business_name = models.CharField(max_length=200)
	public_email = models.EmailField(blank=True)
	public_phone = models.CharField(max_length=32, blank=True)
	show_public_contact = models.BooleanField(default=False)
	categories = models.JSONField(default=list, blank=True)
	verification_status = models.CharField(
		max_length=16, choices=VerificationStatus.choices, default=VerificationStatus.UNVERIFIED,
	)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('business_name', 'pk')
		constraints = [
			models.UniqueConstraint(fields=('organization', 'business_name'), name='unique_supplier_name_in_org'),
		]

	def __str__(self):
		return self.business_name


class CommerceListing(models.Model):
	class Kind(models.TextChoices):
		SERVICE = 'SERVICE', 'Service'
		PRODUCT = 'PRODUCT', 'Product'

	class Availability(models.TextChoices):
		AVAILABLE = 'AVAILABLE', 'Available'
		UNAVAILABLE = 'UNAVAILABLE', 'Unavailable'

	organization = models.ForeignKey(
		Organization, on_delete=models.CASCADE, related_name='commerce_listings',
	)
	supplier = models.ForeignKey(
		SupplierProfile, on_delete=models.PROTECT, related_name='listings',
	)
	kind = models.CharField(max_length=12, choices=Kind.choices)
	category = models.SlugField(max_length=60)
	title = models.CharField(max_length=200)
	description = models.TextField()
	specifications = models.JSONField(default=dict, blank=True)
	price_minor = models.PositiveBigIntegerField(null=True, blank=True)
	currency = models.CharField(max_length=3, default='KES')
	price_unit = models.CharField(max_length=32, default='item')
	availability = models.CharField(max_length=16, choices=Availability.choices, default=Availability.UNAVAILABLE)
	is_published = models.BooleanField(default=False)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='commerce_listings_created',
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('category', 'title', 'pk')
		indexes = [
			models.Index(fields=('kind', 'category', 'is_published'), name='commerce_kind_category_idx'),
			models.Index(fields=('supplier', 'availability'), name='commerce_supp_avail_idx'),
		]
		constraints = [
			models.CheckConstraint(
				check=models.Q(price_minor__isnull=True) | models.Q(price_minor__gt=0),
				name='commerce_price_positive_or_null',
			),
		]

	def clean(self):
		if self.supplier_id and self.organization_id != self.supplier.organization_id:
			from django.core.exceptions import ValidationError
			raise ValidationError({'supplier': 'Supplier must belong to the listing organization.'})

	def __str__(self):
		return self.title


class CommercePhoto(models.Model):
	listing = models.ForeignKey(CommerceListing, on_delete=models.CASCADE, related_name='photos')
	image = models.FileField(upload_to='marketplace/commerce/%Y/%m/')
	file_name = models.CharField(max_length=255)
	content_type = models.CharField(max_length=100)
	caption = models.CharField(max_length=200, blank=True)
	position = models.PositiveSmallIntegerField(default=0)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('position', 'pk')


class CommerceOrder(models.Model):
	class Status(models.TextChoices):
		REQUESTED = 'REQUESTED', 'Requested'
		ACCEPTED = 'ACCEPTED', 'Accepted'
		REJECTED = 'REJECTED', 'Rejected'
		IN_PROGRESS = 'IN_PROGRESS', 'In progress'
		COMPLETED = 'COMPLETED', 'Completed'
		CANCELLED = 'CANCELLED', 'Cancelled'

	listing = models.ForeignKey(CommerceListing, on_delete=models.PROTECT, related_name='orders')
	tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name='commerce_orders')
	requested_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='commerce_orders',
	)
	quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1)
	request_details = models.TextField(blank=True)
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)
	provider_response = models.CharField(max_length=1000, blank=True)
	completed_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('-created_at', '-pk')
		indexes = [
			models.Index(fields=('tenant', '-created_at'), name='commerce_order_tenant_idx'),
			models.Index(fields=('listing', 'status'), name='comm_order_listing_status_idx'),
		]
		constraints = [
			models.CheckConstraint(check=models.Q(quantity__gt=0), name='commerce_order_quantity_positive'),
		]

	@property
	def organization_id(self):
		return self.listing.organization_id

	def __str__(self):
		return f'{self.listing.title} · {self.get_status_display()}'
