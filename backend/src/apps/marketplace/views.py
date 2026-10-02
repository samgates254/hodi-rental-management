from django.db.models import Q
from django.http import FileResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import OrganizationRolePermission, organization_ids_for_resource

from .models import Listing, ListingPhoto
from .serializers import (
	InquiryReadSerializer,
	InquiryWriteSerializer,
	ListingUpdateSerializer,
	ListingWriteSerializer,
	ManagedListingSerializer,
	PublicListingSerializer,
)
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
	update_listing,
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


class InquiryCreateView(APIView):
	authentication_classes = ()
	permission_classes = (AllowAny,)

	def post(self, request):
		serializer = InquiryWriteSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		try:
			listing = publicly_available_queryset().select_related(
				'unit__building__property',
				'created_by',
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
			request=request,
		)
		return Response({'id': inquiry.pk, 'created_at': inquiry.created_at}, status=status.HTTP_201_CREATED)
