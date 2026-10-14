from django.db.models import Q
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from common.permissions import OrganizationRolePermission, organization_ids_for_resource, user_can_access_organization_resource
from application.services.audit import record_audit

from apps.accounts.models import AccountProfile
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Unit

from .models import (
	AgentProfile, AgentUnitAuthorization, CommerceListing, CommerceOrder, CommercePhoto,
	Listing, ListingInquiry, ListingPhoto, SupplierProfile, ViewingRequest,
)
from .serializers import (
	AgentInquiryStatusSerializer,
	AgentProfileSerializer,
	AgentUnitAuthorizationCreateSerializer,
	AgentUnitAuthorizationReadSerializer,
	AgentViewingStatusSerializer,
	InquiryReadSerializer,
	InquiryWriteSerializer,
	ListingUpdateSerializer,
	ListingWriteSerializer,
	CommerceListingSerializer, CommerceOrderSerializer, SupplierProfileSerializer,
	ManagedListingSerializer,
	ViewingRequestReadSerializer,
	PublicListingSerializer,
)


class CommerceListingViewSet(viewsets.ModelViewSet):
	permission_classes = (IsAuthenticated,)
	serializer_class = CommerceListingSerializer
	http_method_names = ('get', 'post', 'patch', 'delete', 'head', 'options')

	def get_queryset(self):
		rows = CommerceListing.objects.select_related('supplier', 'organization').prefetch_related('photos')
		if self.request.method in ('GET', 'HEAD', 'OPTIONS') and self.action in ('list', 'retrieve'):
			if self.request.query_params.get('manage') == '1':
				ids = organization_ids_for_resource(self.request.user, 'marketplace', 'read')
				return rows.filter(organization_id__in=ids)
			rows = rows.filter(is_published=True, availability=CommerceListing.Availability.AVAILABLE,
				supplier__is_active=True, organization__is_active=True)
			kind = self.request.query_params.get('kind')
			category = self.request.query_params.get('category')
			if kind: rows = rows.filter(kind=kind.upper())
			if category: rows = rows.filter(category=category)
			return rows
		ids = organization_ids_for_resource(self.request.user, 'marketplace', 'read' if self.request.method in ('GET','HEAD','OPTIONS') else 'write')
		return rows.filter(organization_id__in=ids)

	def perform_create(self, serializer):
		serializer.save(created_by=self.request.user)

	@action(detail=True, methods=('post',), url_path='photos')
	def photos(self, request, pk=None):
		listing = self.get_object()
		uploaded = request.FILES.get('image')
		if uploaded is None: raise ValidationError({'image': 'Choose a photo to upload.'})
		if listing.photos.count() >= 12: raise ValidationError({'image': 'A listing can have at most 12 photos.'})
		photo = CommercePhoto.objects.create(listing=listing, image=uploaded, file_name=uploaded.name,
			content_type=validate_photo(uploaded), caption=str(request.data.get('caption',''))[:200], position=listing.photos.count())
		record_audit(action='commerce.listing.photo.create', object_type='CommercePhoto', object_id=photo.pk,
			actor=request.user, organization=listing.organization, metadata={'listing_id': listing.pk}, request=request)
		return Response(CommerceListingSerializer(listing, context={'request':request}).data, status=status.HTTP_201_CREATED)

	@action(detail=True, methods=('get','delete'), url_path=r'photos/(?P<photo_id>[^/.]+)')
	def photo(self, request, pk=None, photo_id=None):
		listing = self.get_object()
		try: photo = listing.photos.get(pk=photo_id)
		except (CommercePhoto.DoesNotExist, ValueError) as error: raise NotFound('Photo not found.') from error
		if request.method == 'DELETE':
			photo.delete()
			return Response(status=status.HTTP_204_NO_CONTENT)
		return _photo_response(photo)


class SupplierProfileViewSet(viewsets.ModelViewSet):
	permission_classes = (IsAuthenticated,)
	serializer_class = SupplierProfileSerializer
	http_method_names = ('get', 'post', 'patch', 'head', 'options')
	def get_queryset(self):
		ids = organization_ids_for_resource(self.request.user, 'marketplace', 'read' if self.request.method in ('GET','HEAD','OPTIONS') else 'write')
		return SupplierProfile.objects.filter(organization_id__in=ids)
	def perform_create(self, serializer): serializer.save(created_by=self.request.user)


class CommerceOrderViewSet(viewsets.ModelViewSet):
	permission_classes = (IsAuthenticated,)
	serializer_class = CommerceOrderSerializer
	http_method_names = ('get', 'post', 'patch', 'head', 'options')
	def get_queryset(self):
		from apps.tenants.models import Tenant
		from django.db.models import Q
		ids = organization_ids_for_resource(self.request.user, 'marketplace', 'read')
		return CommerceOrder.objects.select_related('listing__supplier', 'tenant', 'requested_by').filter(
			Q(requested_by=self.request.user) | Q(listing__organization_id__in=ids)).distinct()
	def create(self, request, *args, **kwargs):
		from apps.leases.models import Lease
		from django.utils import timezone
		from rest_framework.exceptions import PermissionDenied
		try: tenant = request.user.tenant_record
		except Exception as error: raise PermissionDenied('An active tenant account is required to place a request.') from error
		if not tenant.is_active or not Lease.objects.filter(tenant=tenant, status='ACTIVE', start_date__lte=timezone.localdate()).filter(Q(end_date__isnull=True)|Q(end_date__gte=timezone.localdate())).exists():
			raise PermissionDenied('An active tenancy is required to place a request.')
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		listing = serializer.validated_data['listing']
		if not listing.is_published or listing.availability != 'AVAILABLE' or not listing.supplier.is_active:
			raise ValidationError({'listing': 'This listing is not currently accepting requests.'})
		order = serializer.save(tenant=tenant, requested_by=request.user)
		record_audit(action='commerce.order.create', object_type='CommerceOrder', object_id=order.pk,
			actor=request.user, organization=listing.organization, metadata={'status': order.status, 'listing_id': listing.pk}, request=request)
		return Response(self.get_serializer(order).data, status=status.HTTP_201_CREATED)
	def partial_update(self, request, *args, **kwargs):
		from rest_framework.exceptions import PermissionDenied
		order = self.get_object()
		if not user_can_access_organization_resource(request.user, order.listing.organization_id, 'marketplace', 'write'):
			raise PermissionDenied('Only the listing provider can update this request.')
		new_status = request.data.get('status')
		allowed = {'REQUESTED': {'ACCEPTED','REJECTED'}, 'ACCEPTED': {'IN_PROGRESS'}, 'IN_PROGRESS': {'COMPLETED'}}
		if new_status == order.status: return Response(self.get_serializer(order).data)
		if new_status not in allowed.get(order.status, set()): raise ValidationError({'status': 'This status transition is not allowed.'})
		order.status = new_status
		if 'provider_response' in request.data: order.provider_response = str(request.data['provider_response'])[:1000]
		if new_status == 'COMPLETED':
			from django.utils import timezone
			order.completed_at = timezone.now()
		order.save(update_fields=('status','provider_response','completed_at','updated_at'))
		record_audit(action='commerce.order.status', object_type='CommerceOrder', object_id=order.pk,
			actor=request.user, organization=order.listing.organization, metadata={'status': order.status}, request=request)
		return Response(self.get_serializer(order).data)
	def destroy(self, request, *args, **kwargs):
		from rest_framework.exceptions import PermissionDenied
		order = self.get_object()
		if order.requested_by_id != request.user.pk or order.status != 'REQUESTED': raise PermissionDenied('Only your pending requests can be cancelled.')
		order.status='CANCELLED'; order.save(update_fields=('status','updated_at'))
		record_audit(action='commerce.order.cancel', object_type='CommerceOrder', object_id=order.pk,
			actor=request.user, organization=order.listing.organization, metadata={'status': order.status}, request=request)
		return Response(self.get_serializer(order).data)
from .services import (
	add_photo,
	create_inquiry,
	create_listing,
	delete_listing,
	delete_photo,
	is_publicly_available,
	publicly_available_queryset,
	publish_listing,
	resolve_managed_unit,
	unpublish_listing,
	pause_listing,
	archive_listing,
	update_listing,
	validate_photo,
)


def _listing_queryset():
	return Listing.objects.select_related(
		'unit__building__property',
		'created_by',
	).prefetch_related('photos')


def _photo_response(photo):
	response = FileResponse(photo.image.open('rb'), content_type=photo.content_type)
	response['Content-Disposition'] = 'inline'
	response['X-Content-Type-Options'] = 'nosniff'
	response['Cache-Control'] = 'private, max-age=3600'
	return response


def _apply_public_filters(queryset, params):
	location = (params.get('location') or '').strip()
	if location:
		queryset = queryset.filter(Q(city__icontains=location) | Q(area__icontains=location))
	min_rent = params.get('min_rent')
	max_rent = params.get('max_rent')
	if min_rent not in (None, ''):
		queryset = queryset.filter(monthly_rent_minor__gte=_rent_bound(min_rent, 'min_rent'))
	if max_rent not in (None, ''):
		queryset = queryset.filter(monthly_rent_minor__lte=_rent_bound(max_rent, 'max_rent'))
	for field in ('bedrooms', 'bathrooms'):
		raw = params.get(field)
		if raw not in (None, ''):
			queryset = queryset.filter(**{field: _count_bound(raw, field)})
	furnished = (params.get('furnished') or '').strip().lower()
	if furnished in {'1', 'true', 'yes'}:
		queryset = queryset.filter(furnished=True)
	elif furnished in {'0', 'false', 'no'}:
		queryset = queryset.filter(furnished=False)
	elif furnished:
		raise ValidationError({'furnished': 'Use true or false.'})
	for amenity in params.getlist('amenity'):
		label = amenity.strip()
		if not label:
			continue
		if any(char in label for char in '"\\%_'):
			raise ValidationError({'amenity': 'Amenity filters cannot include quotes or wildcards.'})
		# JSON containment is unsupported on SQLite. Match the encoded string instead.
		queryset = queryset.filter(amenities__icontains=f'"{label}"')
	ordering = (params.get('ordering') or 'newest').strip()
	if ordering == 'rent':
		queryset = queryset.order_by('monthly_rent_minor', '-created_at')
	elif ordering == '-rent':
		queryset = queryset.order_by('-monthly_rent_minor', '-created_at')
	elif ordering == 'newest':
		queryset = queryset.order_by('-published_at', '-created_at')
	else:
		raise ValidationError({'ordering': 'Use newest, rent, or -rent.'})
	return queryset


def _rent_bound(raw, name):
	try:
		value = int(raw)
	except (TypeError, ValueError) as error:
		raise ValidationError({name: 'Rent filters must be integer cents.'}) from error
	if value < 0:
		raise ValidationError({name: 'Rent filters cannot be negative.'})
	return value


def _count_bound(raw, name):
	try:
		value = int(raw)
	except (TypeError, ValueError) as error:
		raise ValidationError({name: 'Use a whole number.'}) from error
	if value < 0:
		raise ValidationError({name: 'Use a whole number.'})
	return value


class PublicListingViewSet(
	mixins.ListModelMixin,
	mixins.RetrieveModelMixin,
	viewsets.GenericViewSet,
):
	authentication_classes = ()
	permission_classes = (AllowAny,)
	serializer_class = PublicListingSerializer

	def get_queryset(self):
		queryset = publicly_available_queryset().select_related(
			'unit__building__property',
		).prefetch_related('photos')
		if self.action == 'list':
			return _apply_public_filters(queryset, self.request.query_params)
		return queryset

	@action(detail=True, methods=('get',), url_path=r'photos/(?P<photo_id>[^/.]+)')
	def photo(self, request, pk=None, photo_id=None):
		listing = self.get_object()
		return _managed_photo_response(listing, photo_id)


def _managed_photo_response(listing, photo_id):
	try:
		photo = listing.photos.get(pk=photo_id)
	except (ListingPhoto.DoesNotExist, ValueError) as error:
		raise NotFound('Photo not found.') from error
	return _photo_response(photo)


class ManagedListingViewSet(viewsets.ModelViewSet):
	permission_classes = (IsAuthenticated, OrganizationRolePermission)
	organization_resource = 'marketplace'
	http_method_names = ('get', 'post', 'patch', 'delete', 'head', 'options')

	def get_queryset(self):
		organization_ids = organization_ids_for_resource(
			self.request.user,
			'marketplace',
			'read' if self.request.method in ('GET', 'HEAD', 'OPTIONS') else 'write',
		)
		return _listing_queryset().filter(unit__building__property__organization_id__in=organization_ids)

	def get_serializer_class(self):
		if self.action == 'create':
			return ListingWriteSerializer
		if self.action in ('update', 'partial_update'):
			return ListingUpdateSerializer
		return ManagedListingSerializer

	def create(self, request, *args, **kwargs):
		serializer = ListingWriteSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		unit = resolve_managed_unit(request.user, serializer.validated_data['unit'].pk)
		listing = create_listing(
			unit=unit,
			actor=request.user,
			data=serializer.validated_data,
			request=request,
		)
		listing = self.get_queryset().get(pk=listing.pk)
		return Response(ManagedListingSerializer(listing).data, status=status.HTTP_201_CREATED)

	def partial_update(self, request, *args, **kwargs):
		listing = self.get_object()
		serializer = ListingUpdateSerializer(data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		listing = update_listing(
			listing,
			actor=request.user,
			data=serializer.validated_data,
			request=request,
		)
		listing = self.get_queryset().get(pk=listing.pk)
		return Response(ManagedListingSerializer(listing).data)

	def destroy(self, request, *args, **kwargs):
		delete_listing(self.get_object(), actor=request.user, request=request)
		return Response(status=status.HTTP_204_NO_CONTENT)

	@action(detail=True, methods=('post',))
	def publish(self, request, pk=None):
		listing = publish_listing(self.get_object(), actor=request.user, request=request)
		listing = self.get_queryset().get(pk=listing.pk)
		return Response(ManagedListingSerializer(listing).data)

	@action(detail=True, methods=('post',))
	def unpublish(self, request, pk=None):
		listing = unpublish_listing(self.get_object(), actor=request.user, request=request)
		listing = self.get_queryset().get(pk=listing.pk)
		return Response(ManagedListingSerializer(listing).data)

	@action(detail=True, methods=('post',), url_path='photos')
	def photos(self, request, pk=None):
		listing = self.get_object()
		uploaded = request.FILES.get('image')
		if uploaded is None:
			raise ValidationError({'image': 'Choose a photo to upload.'})
		make_primary = str(request.data.get('is_primary', '')).lower() in {'1', 'true', 'yes'}
		add_photo(
			listing,
			uploaded=uploaded,
			caption=request.data.get('caption', ''),
			make_primary=make_primary,
			actor=request.user,
			request=request,
		)
		listing = self.get_queryset().get(pk=listing.pk)
		return Response(ManagedListingSerializer(listing).data, status=status.HTTP_201_CREATED)

	@action(detail=True, methods=('get', 'delete'), url_path=r'photos/(?P<photo_id>[^/.]+)')
	def photo(self, request, pk=None, photo_id=None):
		listing = self.get_object()
		try:
			photo = listing.photos.get(pk=photo_id)
		except (ListingPhoto.DoesNotExist, ValueError) as error:
			raise NotFound('Photo not found.') from error
		if request.method == 'DELETE':
			delete_photo(photo, actor=request.user, request=request)
			return Response(status=status.HTTP_204_NO_CONTENT)
		return _photo_response(photo)

	@action(detail=True, methods=('get',))
	def inquiries(self, request, pk=None):
		listing = self.get_object()
		rows = listing.inquiries.all()
		return Response(InquiryReadSerializer(rows, many=True).data)


def _agent_profile_for(user):
	if not user.is_authenticated or not user.is_active:
		raise PermissionDenied('An active property-agent account is required.')
	if not AccountProfile.objects.filter(
		user=user,
		account_type=AccountProfile.AccountType.PROPERTY_AGENT,
	).exists():
		raise PermissionDenied('A property-agent account is required.')
	try:
		profile = AgentProfile.objects.get(user=user)
	except AgentProfile.DoesNotExist as error:
		raise PermissionDenied('An active property-agent profile is required.') from error
	if profile.account_status != AgentProfile.AccountStatus.ACTIVE:
		raise PermissionDenied('This property-agent account is suspended.')
	return profile


def _active_agent_authorization(profile, unit_id):
	return AgentUnitAuthorization.objects.filter(
		agent=profile,
		unit_id=unit_id,
		status=AgentUnitAuthorization.Status.ACTIVE,
		unit__status__in=(Unit.Status.AVAILABLE, Unit.Status.OCCUPIED, Unit.Status.MAINTENANCE),
		unit__building__property__organization__is_active=True,
	).exists()


class AgentProfileView(APIView):
	permission_classes = (IsAuthenticated,)

	def get(self, request):
		return Response(AgentProfileSerializer(_agent_profile_for(request.user)).data)

	def patch(self, request):
		profile = _agent_profile_for(request.user)
		serializer = AgentProfileSerializer(profile, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		profile = serializer.save()
		record_audit(
			action='marketplace.agent_profile.update',
			object_type='AgentProfile',
			object_id=profile.pk,
			actor=request.user,
			metadata={'updated_fields': sorted(serializer.validated_data.keys())},
			request=request,
		)
		return Response(AgentProfileSerializer(profile).data)


class AgentVerificationRequestView(APIView):
	permission_classes = (IsAuthenticated,)

	def post(self, request):
		profile = _agent_profile_for(request.user)
		if profile.verification_status == AgentProfile.VerificationStatus.PENDING:
			return Response({'verification_status': profile.verification_status})
		if profile.verification_status == AgentProfile.VerificationStatus.VERIFIED:
			return Response({'verification_status': profile.verification_status})
		profile.verification_status = AgentProfile.VerificationStatus.PENDING
		profile.save(update_fields=('verification_status', 'updated_at'))
		record_audit(
			action='marketplace.agent_verification.request',
			object_type='AgentProfile',
			object_id=profile.pk,
			actor=request.user,
			metadata={'verification_status': profile.verification_status},
			request=request,
		)
		return Response({'verification_status': profile.verification_status}, status=status.HTTP_202_ACCEPTED)


class AgentAuthorizedUnitsView(APIView):
	permission_classes = (IsAuthenticated,)

	def get(self, request):
		profile = _agent_profile_for(request.user)
		rows = AgentUnitAuthorization.objects.filter(
			agent=profile,
			status=AgentUnitAuthorization.Status.ACTIVE,
			unit__status__in=(Unit.Status.AVAILABLE, Unit.Status.OCCUPIED, Unit.Status.MAINTENANCE),
			unit__building__property__organization__is_active=True,
		).select_related('unit__building__property').order_by('unit__building__property__name', 'unit__building__name', 'unit__name')
		return Response([
			{
				'authorization_id': row.pk,
				'unit': row.unit_id,
				'unit_name': row.unit.name,
				'building_name': row.unit.building.name,
				'property_name': row.unit.building.property.name,
				'organization': row.unit.organization_id,
				'city': row.unit.building.property.city,
				'bedrooms': row.unit.bedrooms,
				'unit_status': row.unit.status,
				'listing_id': getattr(row.unit, 'marketplace_listing', None).pk
				if hasattr(row.unit, 'marketplace_listing') else None,
			}
			for row in rows
		])


class AgentAuthorizationView(APIView):
	permission_classes = (IsAuthenticated,)

	def _organization(self, request, organization_id):
		try:
			organization = Organization.objects.get(pk=organization_id, is_active=True)
		except (Organization.DoesNotExist, ValueError, TypeError) as error:
			raise NotFound('Organization not found.') from error
		if not OrganizationMembership.objects.filter(
			organization=organization,
			user=request.user,
			role=OrganizationMembership.Role.OWNER,
			is_active=True,
		).exists():
			raise PermissionDenied('Only an active organization owner can authorize a property agent.')
		return organization

	def get(self, request):
		organization = self._organization(request, request.query_params.get('organization'))
		rows = AgentUnitAuthorization.objects.filter(
			unit__building__property__organization=organization,
		).select_related('agent', 'unit__building__property')
		return Response(AgentUnitAuthorizationReadSerializer(rows, many=True).data)

	@transaction.atomic
	def post(self, request):
		serializer = AgentUnitAuthorizationCreateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		data = serializer.validated_data
		organization = self._organization(request, data['organization'])
		try:
			unit = Unit.objects.select_for_update().select_related(
				'building__property__organization',
			).get(
				pk=data['unit'],
				building__property__organization=organization,
				status__in=(Unit.Status.AVAILABLE, Unit.Status.OCCUPIED, Unit.Status.MAINTENANCE),
			)
		except Unit.DoesNotExist as error:
			raise NotFound('An active unit in this organization is required.') from error
		from django.contrib.auth import get_user_model

		User = get_user_model()
		try:
			agent_user = User.objects.get(email__iexact=data['agent_email'], is_active=True)
			agent = AgentProfile.objects.select_for_update().get(user=agent_user)
		except (User.DoesNotExist, AgentProfile.DoesNotExist) as error:
			raise ValidationError({'agent_email': 'A registered active property-agent account is required.'}) from error
		if agent.account_status != AgentProfile.AccountStatus.ACTIVE:
			raise ValidationError({'agent_email': 'This property-agent account is suspended.'})
		active = AgentUnitAuthorization.objects.filter(
			unit=unit,
			status=AgentUnitAuthorization.Status.ACTIVE,
		).select_related('agent').first()
		if active:
			if active.agent_id == agent.pk:
				return Response(AgentUnitAuthorizationReadSerializer(active).data)
			raise ValidationError({'unit': 'This unit already has an active agent authorization. Revoke it before assigning another agent.'})
		authorization = AgentUnitAuthorization.objects.create(
			agent=agent,
			unit=unit,
			granted_by=request.user,
			authority_attestation=(
				'The active organization owner attested that they are authorized to grant '
				'this agent permission to advertise this unit.'
			),
			authority_reference=data.get('authority_reference', '').strip(),
		)
		listing = Listing.objects.select_for_update().filter(unit=unit).first()
		if listing:
			listing.agent_profile = agent
			listing.save(update_fields=('agent_profile', 'updated_at'))
		record_audit(
			action='marketplace.agent_authorization.grant',
			object_type='AgentUnitAuthorization',
			object_id=authorization.pk,
			actor=request.user,
			organization=organization,
			metadata={'agent_id': agent.pk, 'unit_id': unit.pk},
			request=request,
		)
		return Response(AgentUnitAuthorizationReadSerializer(authorization).data, status=status.HTTP_201_CREATED)

	@transaction.atomic
	def delete(self, request, authorization_id):
		try:
			authorization = AgentUnitAuthorization.objects.select_for_update().select_related(
				'agent', 'unit__building__property__organization',
			).get(pk=authorization_id)
		except AgentUnitAuthorization.DoesNotExist as error:
			raise NotFound('Agent authorization not found.') from error
		organization = authorization.unit.building.property.organization
		self._organization(request, organization.pk)
		if authorization.status == AgentUnitAuthorization.Status.REVOKED:
			return Response(AgentUnitAuthorizationReadSerializer(authorization).data)
		authorization.status = AgentUnitAuthorization.Status.REVOKED
		authorization.revoked_at = timezone.now()
		authorization.revoked_by = request.user
		authorization.save(update_fields=('status', 'revoked_at', 'revoked_by'))
		listing = Listing.objects.select_for_update().filter(
			unit=authorization.unit,
			agent_profile=authorization.agent,
		).first()
		if listing:
			if listing.status == Listing.Status.PUBLISHED:
				pause_listing(listing, actor=request.user, request=request)
			listing.agent_profile = None
			listing.save(update_fields=('agent_profile', 'updated_at'))
		record_audit(
			action='marketplace.agent_authorization.revoke',
			object_type='AgentUnitAuthorization',
			object_id=authorization.pk,
			actor=request.user,
			organization=organization,
			metadata={'agent_id': authorization.agent_id, 'unit_id': authorization.unit_id},
			request=request,
		)
		return Response(AgentUnitAuthorizationReadSerializer(authorization).data)


class AgentListingViewSet(viewsets.ModelViewSet):
	permission_classes = (IsAuthenticated,)
	serializer_class = ManagedListingSerializer
	http_method_names = ('get', 'post', 'patch', 'head', 'options')

	def profile(self):
		return _agent_profile_for(self.request.user)

	def get_queryset(self):
		profile = self.profile()
		return _listing_queryset().filter(
			agent_profile=profile,
			unit__agent_authorizations__agent=profile,
			unit__agent_authorizations__status=AgentUnitAuthorization.Status.ACTIVE,
			unit__status__in=(Unit.Status.AVAILABLE, Unit.Status.OCCUPIED, Unit.Status.MAINTENANCE),
			unit__building__property__organization__is_active=True,
		).distinct()

	def list(self, request, *args, **kwargs):
		self.serializer_class = ManagedListingSerializer
		return super().list(request, *args, **kwargs)

	def create(self, request, *args, **kwargs):
		profile = self.profile()
		serializer = ListingWriteSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		unit_id = serializer.validated_data['unit'].pk
		if not _active_agent_authorization(profile, unit_id):
			raise NotFound('Authorized unit not found.')
		unit = Unit.objects.select_related('building__property__organization').get(pk=unit_id)
		listing = create_listing(
			unit=unit,
			actor=request.user,
			data=serializer.validated_data,
			request=request,
			agent_profile=profile,
		)
		listing = self.get_queryset().get(pk=listing.pk)
		return Response(ManagedListingSerializer(listing).data, status=status.HTTP_201_CREATED)

	def partial_update(self, request, *args, **kwargs):
		profile = self.profile()
		listing = self.get_object()
		if listing.agent_profile_id != profile.pk or not _active_agent_authorization(profile, listing.unit_id):
			raise PermissionDenied('This listing is no longer authorized for editing.')
		serializer = ListingUpdateSerializer(data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		listing = update_listing(listing, actor=request.user, data=serializer.validated_data, request=request)
		return Response(ManagedListingSerializer(self.get_queryset().get(pk=listing.pk)).data)

	@action(detail=True, methods=('post',))
	def publish(self, request, pk=None):
		profile = self.profile()
		listing = self.get_object()
		if profile.verification_status != AgentProfile.VerificationStatus.VERIFIED:
			raise PermissionDenied('Your agent profile must be verified before you can publish listings.')
		if listing.agent_profile_id != profile.pk or not _active_agent_authorization(profile, listing.unit_id):
			raise PermissionDenied('An active owner authorization is required to publish this listing.')
		listing = publish_listing(listing, actor=request.user, request=request)
		return Response(ManagedListingSerializer(self.get_queryset().get(pk=listing.pk)).data)

	@action(detail=True, methods=('post',))
	def pause(self, request, pk=None):
		profile = self.profile()
		listing = self.get_object()
		if listing.agent_profile_id != profile.pk or not _active_agent_authorization(profile, listing.unit_id):
			raise PermissionDenied('This listing is no longer authorized for management.')
		listing = pause_listing(listing, actor=request.user, request=request)
		return Response(ManagedListingSerializer(self.get_queryset().get(pk=listing.pk)).data)

	@action(detail=True, methods=('post',))
	def archive(self, request, pk=None):
		profile = self.profile()
		listing = self.get_object()
		if listing.agent_profile_id != profile.pk or not _active_agent_authorization(profile, listing.unit_id):
			raise PermissionDenied('This listing is no longer authorized for management.')
		listing = archive_listing(listing, actor=request.user, request=request)
		return Response(ManagedListingSerializer(self.get_queryset().get(pk=listing.pk)).data)

	@action(detail=True, methods=('post',), url_path='photos')
	def photos(self, request, pk=None):
		listing = self.get_object()
		if listing.agent_profile_id != self.profile().pk or not _active_agent_authorization(self.profile(), listing.unit_id):
			raise PermissionDenied('This listing is no longer authorized for editing.')
		uploaded = request.FILES.get('image')
		if uploaded is None:
			raise ValidationError({'image': 'Choose a photo to upload.'})
		make_primary = str(request.data.get('is_primary', '')).lower() in {'1', 'true', 'yes'}
		add_photo(listing, uploaded=uploaded, caption=request.data.get('caption', ''),
			make_primary=make_primary, actor=request.user, request=request)
		return Response(ManagedListingSerializer(self.get_queryset().get(pk=listing.pk)).data, status=status.HTTP_201_CREATED)


class AgentInquiryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
	permission_classes = (IsAuthenticated,)
	serializer_class = InquiryReadSerializer
	http_method_names = ('get', 'patch', 'head', 'options')

	def get_queryset(self):
		profile = _agent_profile_for(self.request.user)
		return ListingInquiry.objects.filter(
			listing__agent_profile=profile,
			listing__unit__agent_authorizations__agent=profile,
			listing__unit__agent_authorizations__status=AgentUnitAuthorization.Status.ACTIVE,
			listing__unit__status__in=(Unit.Status.AVAILABLE, Unit.Status.OCCUPIED, Unit.Status.MAINTENANCE),
			listing__unit__building__property__organization__is_active=True,
		).select_related('listing', 'listing__unit').prefetch_related('viewing_request').distinct()

	@action(detail=True, methods=('patch',), url_path='status')
	def status_update(self, request, pk=None):
		inquiry = self.get_object()
		serializer = AgentInquiryStatusSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		new_status = serializer.validated_data['status']
		allowed = {
			ListingInquiry.Status.NEW: {ListingInquiry.Status.CONTACTED, ListingInquiry.Status.CLOSED},
			ListingInquiry.Status.CONTACTED: {ListingInquiry.Status.CLOSED},
			ListingInquiry.Status.CLOSED: set(),
		}
		if new_status != inquiry.status and new_status not in allowed[inquiry.status]:
			raise ValidationError({'status': 'This enquiry status change is not allowed.'})
		if new_status != inquiry.status:
			inquiry.status = new_status
			inquiry.save(update_fields=('status',))
			record_audit(
				action='marketplace.inquiry.status',
				object_type='ListingInquiry',
				object_id=inquiry.pk,
				actor=request.user,
				organization=inquiry.listing.unit.building.property.organization,
				metadata={'status': inquiry.status, 'listing_id': str(inquiry.listing_id)},
				request=request,
			)
		return Response(self.get_serializer(inquiry).data)


class AgentViewingRequestViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
	permission_classes = (IsAuthenticated,)
	serializer_class = ViewingRequestReadSerializer
	http_method_names = ('get', 'patch', 'head', 'options')

	def get_queryset(self):
		profile = _agent_profile_for(self.request.user)
		return ViewingRequest.objects.filter(
			inquiry__listing__agent_profile=profile,
			inquiry__listing__unit__agent_authorizations__agent=profile,
			inquiry__listing__unit__agent_authorizations__status=AgentUnitAuthorization.Status.ACTIVE,
			inquiry__listing__unit__status__in=(Unit.Status.AVAILABLE, Unit.Status.OCCUPIED, Unit.Status.MAINTENANCE),
			inquiry__listing__unit__building__property__organization__is_active=True,
		).select_related('inquiry__listing__unit__building__property').distinct()

	@action(detail=True, methods=('patch',), url_path='status')
	def status_update(self, request, pk=None):
		viewing = self.get_object()
		serializer = AgentViewingStatusSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		new_status = serializer.validated_data['status']
		allowed = {
			ViewingRequest.Status.REQUESTED: {
				ViewingRequest.Status.CONFIRMED,
				ViewingRequest.Status.DECLINED,
				ViewingRequest.Status.CANCELLED,
			},
			ViewingRequest.Status.CONFIRMED: {
				ViewingRequest.Status.CANCELLED,
				ViewingRequest.Status.COMPLETED,
			},
		}
		if new_status != viewing.status and new_status not in allowed.get(viewing.status, set()):
			raise ValidationError({'status': 'This viewing status change is not allowed.'})
		if new_status == ViewingRequest.Status.COMPLETED and viewing.requested_for > timezone.now():
			raise ValidationError({'status': 'A future viewing cannot be marked completed.'})
		if new_status != viewing.status:
			viewing.status = new_status
			viewing.save(update_fields=('status', 'updated_at'))
			record_audit(
				action='marketplace.viewing.status',
				object_type='ViewingRequest',
				object_id=viewing.pk,
				actor=request.user,
				organization=viewing.inquiry.listing.unit.building.property.organization,
				metadata={'status': viewing.status, 'listing_id': str(viewing.inquiry.listing_id)},
				request=request,
			)
		return Response(self.get_serializer(viewing).data)


class AgentProfileModerationView(APIView):
	permission_classes = (IsAuthenticated, permissions.IsAdminUser)

	@transaction.atomic
	def post(self, request, profile_id):
		try:
			profile = AgentProfile.objects.select_related('user').get(pk=profile_id)
		except AgentProfile.DoesNotExist as error:
			raise NotFound('Agent profile not found.') from error
		verification_status = request.data.get('verification_status', profile.verification_status)
		account_status = request.data.get('account_status', profile.account_status)
		valid_verification = {choice for choice, _label in AgentProfile.VerificationStatus.choices}
		valid_account = {choice for choice, _label in AgentProfile.AccountStatus.choices}
		if not isinstance(verification_status, str) or verification_status not in valid_verification:
			raise ValidationError({'verification_status': 'Choose a valid verification status.'})
		if not isinstance(account_status, str) or account_status not in valid_account:
			raise ValidationError({'account_status': 'Choose a valid account status.'})
		profile.verification_status = verification_status
		profile.account_status = account_status
		profile.save(update_fields=('verification_status', 'account_status', 'updated_at'))
		if (verification_status != AgentProfile.VerificationStatus.VERIFIED
				or account_status != AgentProfile.AccountStatus.ACTIVE):
			listings = Listing.objects.filter(agent_profile=profile, status=Listing.Status.PUBLISHED)
			for listing in listings.select_related('unit__building__property'):
				pause_listing(listing, actor=request.user, request=request)
		record_audit(
			action='marketplace.agent_profile.moderate',
			object_type='AgentProfile',
			object_id=profile.pk,
			actor=request.user,
			metadata={'verification_status': profile.verification_status, 'account_status': profile.account_status},
			request=request,
		)
		return Response(AgentProfileSerializer(profile).data)


class InquiryCreateView(APIView):
	authentication_classes = ()
	permission_classes = (AllowAny,)
	throttle_classes = (ScopedRateThrottle,)
	throttle_scope = 'marketplace_inquiry'

	def post(self, request):
		serializer = InquiryWriteSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		try:
			listing = publicly_available_queryset().select_related(
				'unit__building__property',
				'created_by',
				'agent_profile__user',
			).get(pk=serializer.validated_data['listing'])
		except Listing.DoesNotExist as error:
			raise NotFound('Listing not found.') from error
		if not is_publicly_available(listing):
			raise NotFound('Listing not found.')
		inquiry = create_inquiry(
			listing=listing,
			name=serializer.validated_data['name'],
			email=serializer.validated_data['email'],
			phone=serializer.validated_data.get('phone', ''),
			message=serializer.validated_data['message'],
			viewing_requested_for=serializer.validated_data.get('viewing_requested_for'),
			request=request,
		)
		return Response({'id': inquiry.pk, 'created_at': inquiry.created_at}, status=status.HTTP_201_CREATED)
