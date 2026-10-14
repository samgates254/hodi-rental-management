from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.leases.models import Lease
from apps.properties.models import Unit
from application.services.audit import record_audit
from application.services.notifications import notify_user
from common.permissions import user_can_access_organization_resource

from .models import AgentProfile, Listing, ListingInquiry, ListingPhoto, ViewingRequest

MAX_PHOTOS = 12
MAX_PHOTO_BYTES = 8 * 1024 * 1024
IMAGE_TYPES = {
	'image/jpeg': {'jpg', 'jpeg'},
	'image/png': {'png'},
	'image/webp': {'webp'},
	'image/gif': {'gif'},
}


def publicly_available_queryset():
	active_lease = Lease.objects.filter(
		unit_id=OuterRef('unit_id'),
		status=Lease.Status.ACTIVE,
	)
	return (
		Listing.objects.filter(
			status=Listing.Status.PUBLISHED,
			unit__status=Unit.Status.AVAILABLE,
		)
		.filter(
			Q(agent_profile__isnull=True)
			| Q(
				agent_profile__verification_status=AgentProfile.VerificationStatus.VERIFIED,
				agent_profile__account_status=AgentProfile.AccountStatus.ACTIVE,
				agent_profile__user__is_active=True,
			)
		)
		.annotate(has_active_lease=Exists(active_lease))
		.filter(has_active_lease=False)
	)


def is_publicly_available(listing):
	if listing.status != Listing.Status.PUBLISHED:
		return False
	if listing.agent_profile_id and (
		listing.agent_profile.verification_status != AgentProfile.VerificationStatus.VERIFIED
		or listing.agent_profile.account_status != AgentProfile.AccountStatus.ACTIVE
		or not listing.agent_profile.user.is_active
	):
		return False
	if listing.unit.status != Unit.Status.AVAILABLE:
		return False
	return not listing.unit.leases.filter(status=Lease.Status.ACTIVE).exists()


def _organization(unit):
	return unit.building.property.organization


def resolve_managed_unit(user, unit_id):
	try:
		unit = Unit.objects.select_related('building__property__organization').get(pk=unit_id)
	except (Unit.DoesNotExist, ValueError, TypeError) as error:
		raise NotFound('Unit not found.') from error
	if not user_can_access_organization_resource(user, unit.organization_id, 'marketplace', 'write'):
		raise NotFound('Unit not found.')
	return unit


def _clean_amenities(value):
	if value is None:
		return []
	if not isinstance(value, list):
		raise ValidationError({'amenities': 'Amenities must be a list of labels.'})
	cleaned = []
	seen = set()
	for item in value:
		if not isinstance(item, str):
			raise ValidationError({'amenities': 'Each amenity must be text.'})
		label = ' '.join(item.split())
		if not label:
			continue
		if len(label) > 40:
			raise ValidationError({'amenities': 'Each amenity must be 40 characters or fewer.'})
		key = label.casefold()
		if key in seen:
			continue
		seen.add(key)
		cleaned.append(label)
		if len(cleaned) > 30:
			raise ValidationError({'amenities': 'Add at most 30 amenities.'})
	return cleaned


def _clean_rent(amount):
	if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
		raise ValidationError({'monthly_rent_minor': 'Rent must be a positive integer number of cents.'})
	return amount


def _clean_currency(value):
	currency = (value or 'KES').strip().upper()
	if currency != 'KES':
		raise ValidationError({'currency': 'Marketplace rent is recorded in KES cents.'})
	return currency


def _apply_fields(listing, data, unit):
	if 'monthly_rent_minor' in data:
		listing.monthly_rent_minor = _clean_rent(data['monthly_rent_minor'])
	if 'currency' in data:
		listing.currency = _clean_currency(data['currency'])
	if 'amenities' in data:
		listing.amenities = _clean_amenities(data['amenities'])
	for field in ('title', 'description', 'bedrooms', 'bathrooms', 'floor', 'size_sqm', 'furnished', 'area', 'city', 'country'):
		if field in data:
			setattr(listing, field, data[field])
	if not (listing.city or '').strip():
		listing.city = unit.building.property.city
	if not (listing.city or '').strip():
		raise ValidationError({'city': 'A city is required.'})
	if not (listing.title or '').strip():
		raise ValidationError({'title': 'A title is required.'})
	return listing


@transaction.atomic
def create_listing(*, unit, actor, data, request=None, agent_profile=None):
	if Listing.objects.filter(unit=unit).exists():
		raise ValidationError({'unit': 'This unit already has a marketplace listing.'})
	listing = Listing(
		unit=unit,
		created_by=actor,
		agent_profile=agent_profile,
		title=data.get('title', ''),
		description=data.get('description', ''),
		monthly_rent_minor=_clean_rent(data.get('monthly_rent_minor')),
		currency=_clean_currency(data.get('currency', 'KES')),
		bedrooms=data.get('bedrooms', unit.bedrooms or 0),
		bathrooms=data.get('bathrooms', 0),
		floor=data.get('floor'),
		size_sqm=data.get('size_sqm'),
		furnished=bool(data.get('furnished', False)),
		amenities=_clean_amenities(data.get('amenities', [])),
		area=(data.get('area') or '').strip(),
		city=(data.get('city') or unit.building.property.city or '').strip(),
		country=(data.get('country') or unit.building.property.country or 'Kenya').strip() or 'Kenya',
		status=Listing.Status.DRAFT,
	)
	if not listing.title:
		raise ValidationError({'title': 'A title is required.'})
	if not listing.city:
		raise ValidationError({'city': 'A city is required.'})
	listing.save()
	record_audit(
		action='marketplace.listing.create',
		object_type='Listing',
		object_id=listing.pk,
		actor=actor,
		organization=_organization(unit),
		metadata={'unit_id': unit.pk},
		request=request,
	)
	return listing


@transaction.atomic
def update_listing(listing, *, actor, data, request=None):
	listing = Listing.objects.select_for_update(of=('self',)).select_related('unit__building__property').get(pk=listing.pk)
	if 'unit' in data and data['unit'] is not None and data['unit'].pk != listing.unit_id:
		raise ValidationError({'unit': 'A listing cannot be moved to another unit.'})
	_apply_fields(listing, data, listing.unit)
	listing.save()
	record_audit(
		action='marketplace.listing.update',
		object_type='Listing',
		object_id=listing.pk,
		actor=actor,
		organization=_organization(listing.unit),
		metadata={'unit_id': listing.unit_id},
		request=request,
	)
	return listing


def _availability_error(listing):
	if listing.unit.status != Unit.Status.AVAILABLE:
		return 'Only an available unit can be published.'
	if listing.unit.leases.filter(status=Lease.Status.ACTIVE).exists():
		return 'A unit with an active lease cannot be published.'
	return ''


@transaction.atomic
def publish_listing(listing, *, actor, request=None):
	listing = Listing.objects.select_for_update(of=('self',)).select_related('unit__building__property').get(pk=listing.pk)
	reason = _availability_error(listing)
	if reason:
		raise ValidationError({'status': reason})
	listing.status = Listing.Status.PUBLISHED
	listing.published_at = timezone.now()
	listing.save(update_fields=('status', 'published_at', 'updated_at'))
	record_audit(
		action='marketplace.listing.publish',
		object_type='Listing',
		object_id=listing.pk,
		actor=actor,
		organization=_organization(listing.unit),
		metadata={'unit_id': listing.unit_id},
		request=request,
	)
	return listing


@transaction.atomic
def unpublish_listing(listing, *, actor, request=None):
	listing = Listing.objects.select_for_update(of=('self',)).select_related('unit__building__property').get(pk=listing.pk)
	listing.status = Listing.Status.DRAFT
	listing.save(update_fields=('status', 'updated_at'))
	record_audit(
		action='marketplace.listing.unpublish',
		object_type='Listing',
		object_id=listing.pk,
		actor=actor,
		organization=_organization(listing.unit),
		metadata={'unit_id': listing.unit_id},
		request=request,
	)
	return listing


@transaction.atomic
def pause_listing(listing, *, actor, request=None):
	listing = Listing.objects.select_for_update(of=('self',)).select_related('unit__building__property').get(pk=listing.pk)
	listing.status = Listing.Status.PAUSED
	listing.save(update_fields=('status', 'updated_at'))
	record_audit(
		action='marketplace.listing.pause',
		object_type='Listing',
		object_id=listing.pk,
		actor=actor,
		organization=_organization(listing.unit),
		metadata={'unit_id': listing.unit_id},
		request=request,
	)
	return listing


@transaction.atomic
def archive_listing(listing, *, actor, request=None):
	listing = Listing.objects.select_for_update(of=('self',)).select_related('unit__building__property').get(pk=listing.pk)
	listing.status = Listing.Status.ARCHIVED
	listing.save(update_fields=('status', 'updated_at'))
	record_audit(
		action='marketplace.listing.archive',
		object_type='Listing',
		object_id=listing.pk,
		actor=actor,
		organization=_organization(listing.unit),
		metadata={'unit_id': listing.unit_id},
		request=request,
	)
	return listing


@transaction.atomic
def delete_listing(listing, *, actor, request=None):
	listing = Listing.objects.select_for_update(of=('self',)).select_related('unit__building__property').get(pk=listing.pk)
	organization = _organization(listing.unit)
	unit_id = listing.unit_id
	listing_id = listing.pk
	for photo in listing.photos.all():
		photo.image.delete(save=False)
	listing.delete()
	record_audit(
		action='marketplace.listing.delete',
		object_type='Listing',
		object_id=listing_id,
		actor=actor,
		organization=organization,
		metadata={'unit_id': unit_id},
		request=request,
	)


def _extension(name):
	return (name or '').rsplit('.', 1)[-1].lower() if '.' in (name or '') else ''


def validate_photo(uploaded):
	content_type = (getattr(uploaded, 'content_type', '') or '').split(';')[0].strip().lower()
	allowed = IMAGE_TYPES.get(content_type)
	if allowed is None:
		raise ValidationError({'image': 'Upload a JPEG, PNG, WEBP, or GIF photo.'})
	if _extension(uploaded.name) not in allowed:
		raise ValidationError({'image': 'The file extension does not match the image type.'})
	if uploaded.size > MAX_PHOTO_BYTES:
		raise ValidationError({'image': 'Each photo must be 8 MB or smaller.'})
	return content_type


@transaction.atomic
def add_photo(listing, *, uploaded, caption='', make_primary=False, actor, request=None):
	listing = Listing.objects.select_for_update(of=('self',)).get(pk=listing.pk)
	if listing.photos.count() >= MAX_PHOTOS:
		raise ValidationError({'image': f'A listing can have at most {MAX_PHOTOS} photos.'})
	content_type = validate_photo(uploaded)
	position = (listing.photos.order_by('-position').values_list('position', flat=True).first() or 0) + 1
	is_primary = make_primary or not listing.photos.filter(is_primary=True).exists()
	if is_primary:
		listing.photos.filter(is_primary=True).update(is_primary=False)
	photo = ListingPhoto.objects.create(
		listing=listing,
		image=uploaded,
		file_name=uploaded.name.rsplit('/', 1)[-1][:255],
		content_type=content_type,
		caption=(caption or '').strip()[:200],
		position=position,
		is_primary=is_primary,
	)
	record_audit(
		action='marketplace.photo.add',
		object_type='ListingPhoto',
		object_id=photo.pk,
		actor=actor,
		organization=_organization(listing.unit),
		metadata={'listing_id': str(listing.pk)},
		request=request,
	)
	return photo


@transaction.atomic
def delete_photo(photo, *, actor, request=None):
	listing = Listing.objects.select_for_update(of=('self',)).get(pk=photo.listing_id)
	was_primary = photo.is_primary
	photo_id = photo.pk
	photo.image.delete(save=False)
	photo.delete()
	if was_primary:
		successor = listing.photos.order_by('position', 'pk').first()
		if successor is not None:
			successor.is_primary = True
			successor.save(update_fields=('is_primary',))
	record_audit(
		action='marketplace.photo.delete',
		object_type='ListingPhoto',
		object_id=photo_id,
		actor=actor,
		organization=_organization(listing.unit),
		metadata={'listing_id': str(listing.pk)},
		request=request,
	)


@transaction.atomic
def create_inquiry(*, listing, name, email, phone, message, viewing_requested_for=None, request=None):
	if not is_publicly_available(listing):
		raise NotFound('Listing not found.')
	inquiry = ListingInquiry.objects.create(
		listing=listing,
		name=name.strip(),
		email=email.strip(),
		phone=(phone or '').strip(),
		message=message.strip(),
	)
	if viewing_requested_for is not None:
		viewing = ViewingRequest.objects.create(
			inquiry=inquiry,
			requested_for=viewing_requested_for,
		)
		record_audit(
			action='marketplace.viewing.create',
			object_type='ViewingRequest',
			object_id=viewing.pk,
			actor=None,
			organization=_organization(listing.unit),
			metadata={'listing_id': str(listing.pk)},
			request=request,
		)
	record_audit(
		action='marketplace.inquiry.create',
		object_type='ListingInquiry',
		object_id=inquiry.pk,
		actor=None,
		organization=_organization(listing.unit),
		metadata={'listing_id': str(listing.pk)},
		request=request,
	)
	notify_user(
		user=listing.agent_profile.user if listing.agent_profile_id else listing.created_by,
		type='MARKETPLACE_INQUIRY',
		title='New listing inquiry',
		body=f'{inquiry.name} asked about {listing.title}.',
		organization=_organization(listing.unit),
		payload={'listing_id': str(listing.pk), 'inquiry_id': inquiry.pk},
	)
	return inquiry
