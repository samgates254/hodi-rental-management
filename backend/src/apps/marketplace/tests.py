import tempfile
from datetime import date, datetime, timezone as datetime_timezone
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.leases.models import Lease
from apps.audit.models import AuditLog
from apps.marketplace.models import CommerceListing, CommerceOrder, SupplierProfile, Listing, ListingInquiry, ListingPhoto
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant

MEDIA_ROOT = tempfile.mkdtemp(prefix='hodi-mkt-')
PNG = (
	b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
	b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
	b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)


def photo_file(name='room.png', content_type='image/png', body=PNG):
	return SimpleUploadedFile(name, body, content_type=content_type)


def public_results(response):
	return response.data.get('results', []) if isinstance(response.data, dict) else response.data


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class MarketplaceApiTests(APITestCase):
	def setUp(self):
		User = get_user_model()
		self.owner = User.objects.create_user(username='mkt-owner', password='password')
		self.manager = User.objects.create_user(username='mkt-manager', password='password')
		self.accountant = User.objects.create_user(username='mkt-accountant', password='password')
		self.caretaker = User.objects.create_user(username='mkt-caretaker', password='password')
		self.tenant_user = User.objects.create_user(username='mkt-tenant', password='password')
		self.other = User.objects.create_user(username='mkt-other', password='password')
		self.organization = Organization.objects.create(name='Kilimani Homes')
		self.other_organization = Organization.objects.create(name='Other Homes')
		self._member(self.organization, self.owner, OrganizationMembership.Role.OWNER)
		self._member(self.organization, self.manager, OrganizationMembership.Role.PROPERTY_MANAGER)
		self._member(self.organization, self.accountant, OrganizationMembership.Role.ACCOUNTANT)
		self._member(self.organization, self.caretaker, OrganizationMembership.Role.CARETAKER)
		self._member(self.other_organization, self.other, OrganizationMembership.Role.OWNER)
		self.unit = self._unit(self.organization, 'Acacia Court', 'Block A', 'A-01', city='Nairobi')
		self.other_unit = self._unit(self.other_organization, 'Hidden Court', 'Block B', 'B-01', city='Kisumu')
		Tenant.objects.create(
			organization=self.organization,
			user=self.tenant_user,
			first_name='Amina',
			last_name='Otieno',
			phone_number='+254700000001',
			email='amina@example.com',
			national_id='SECRET-ID',
		)

	def _member(self, organization, user, role):
		OrganizationMembership.objects.create(organization=organization, user=user, role=role)

	def _unit(self, organization, property_name, building_name, unit_name, city):
		property_record = Property.objects.create(
			organization=organization,
			name=property_name,
			city=city,
		)
		building = Building.objects.create(property=property_record, name=building_name)
		return Unit.objects.create(building=building, name=unit_name, bedrooms=1)

	def _payload(self, unit, **extra):
		data = {
			'unit': unit.pk,
			'title': 'Bright one-bedroom in Kilimani',
			'description': 'Quiet courtyard unit.',
			'monthly_rent_minor': 4500000,
			'bedrooms': 1,
			'bathrooms': 1,
			'furnished': True,
			'amenities': ['Water', 'Parking'],
			'area': 'Kilimani',
			'city': 'Nairobi',
		}
		data.update(extra)
		return data

	def _create(self, unit=None, user=None, **extra):
		self.client.force_authenticate(user or self.owner)
		return self.client.post(
			reverse('marketplace:managed-listing-list'),
			self._payload(unit or self.unit, **extra),
			format='json',
		)

	def _publish(self, listing_id, user=None):
		self.client.force_authenticate(user or self.owner)
		return self.client.post(
			reverse('marketplace:managed-listing-publish', kwargs={'pk': listing_id}),
		)

	def test_unauthenticated_browse_is_empty_until_a_listing_is_published(self):
		response = self.client.get(reverse('marketplace:public-listing-list'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(public_results(response), [])

		created = self._create()
		self.assertEqual(created.status_code, status.HTTP_201_CREATED)
		self.client.force_authenticate(None)
		hidden = self.client.get(reverse('marketplace:public-listing-list'))
		self.assertEqual(public_results(hidden), [])
		detail = self.client.get(
			reverse('marketplace:public-listing-detail', kwargs={'pk': created.data['id']}),
		)
		self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

		published = self._publish(created.data['id'])
		self.assertEqual(published.status_code, status.HTTP_200_OK)
		self.assertEqual(published.data['status'], Listing.Status.PUBLISHED)
		self.client.force_authenticate(None)
		visible = self.client.get(reverse('marketplace:public-listing-list'))
		self.assertEqual(len(public_results(visible)), 1)
		row = public_results(visible)[0]
		self.assertEqual(row['title'], 'Bright one-bedroom in Kilimani')
		self.assertTrue(row['available'])
		self.assertNotIn('unit', row)
		self.assertNotIn('organization', row)
		self.assertNotIn('status', row)
		self.assertNotIn('created_by', row)
		body = visible.content.decode()
		self.assertNotIn('SECRET-ID', body)
		self.assertNotIn('amina@example.com', body)
		self.assertNotIn('+254700000001', body)

	def test_listing_rent_above_storage_range_is_field_validation(self):
		response = self._create(monthly_rent_minor=1 << 63)
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('monthly_rent_minor', response.data)
		self.assertFalse(Listing.objects.exists())

	def test_public_filters_and_ordering(self):
		first = self._create(title='Cheaper studio', monthly_rent_minor=2500000, bedrooms=0, bathrooms=1, furnished=False, amenities=['Water'], area='Westlands')
		second_unit = self._unit(self.organization, 'Acacia Court 2', 'Block C', 'C-02', city='Nairobi')
		second = self._create(unit=second_unit, title='Furnished two-bed', monthly_rent_minor=8000000, bedrooms=2, bathrooms=2, furnished=True, amenities=['Parking'], city='Mombasa', area='Nyali')
		self._publish(first.data['id'])
		self._publish(second.data['id'])
		self.client.force_authenticate(None)

		by_city = self.client.get(reverse('marketplace:public-listing-list'), {'location': 'mombasa'})
		self.assertEqual([row['title'] for row in public_results(by_city)], ['Furnished two-bed'])

		by_rent = self.client.get(reverse('marketplace:public-listing-list'), {'min_rent': 3000000, 'max_rent': 9000000})
		self.assertEqual([row['title'] for row in public_results(by_rent)], ['Furnished two-bed'])

		by_rooms = self.client.get(reverse('marketplace:public-listing-list'), {'bedrooms': 0, 'bathrooms': 1, 'furnished': 'false'})
		self.assertEqual([row['title'] for row in public_results(by_rooms)], ['Cheaper studio'])

		by_amenity = self.client.get(reverse('marketplace:public-listing-list'), {'amenity': 'Parking'})
		self.assertEqual([row['title'] for row in public_results(by_amenity)], ['Furnished two-bed'])

		ordered = self.client.get(reverse('marketplace:public-listing-list'), {'ordering': 'rent'})
		self.assertEqual([row['monthly_rent_minor'] for row in public_results(ordered)], [2500000, 8000000])
		desc = self.client.get(reverse('marketplace:public-listing-list'), {'ordering': '-rent'})
		self.assertEqual([row['monthly_rent_minor'] for row in public_results(desc)], [8000000, 2500000])

		invalid = self.client.get(reverse('marketplace:public-listing-list'), {'ordering': 'title'})
		self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

	def test_occupied_unit_and_active_lease_are_not_public(self):
		created = self._create()
		self.unit.status = Unit.Status.OCCUPIED
		self.unit.save(update_fields=('status',))
		rejected = self._publish(created.data['id'])
		self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('status', rejected.data)

		self.unit.status = Unit.Status.AVAILABLE
		self.unit.save(update_fields=('status',))
		published = self._publish(created.data['id'])
		self.assertEqual(published.status_code, status.HTTP_200_OK)

		self.unit.status = Unit.Status.OCCUPIED
		self.unit.save(update_fields=('status',))
		self.client.force_authenticate(None)
		self.assertEqual(public_results(self.client.get(reverse('marketplace:public-listing-list'))), [])
		self.assertEqual(
			self.client.get(reverse('marketplace:public-listing-detail', kwargs={'pk': created.data['id']})).status_code,
			status.HTTP_404_NOT_FOUND,
		)

		self.unit.status = Unit.Status.AVAILABLE
		self.unit.save(update_fields=('status',))
		tenant = Tenant.objects.get(user=self.tenant_user)
		Lease.objects.create(
			tenant=tenant,
			unit=self.unit,
			reference='L-ACTIVE',
			start_date=date(2026, 1, 1),
			monthly_rent_minor=4500000,
			status=Lease.Status.ACTIVE,
		)
		self.assertEqual(public_results(self.client.get(reverse('marketplace:public-listing-list'))), [])

	def test_manager_can_update_unpublish_and_cannot_duplicate(self):
		created = self._create(user=self.manager)
		self.assertEqual(created.status_code, status.HTTP_201_CREATED)
		listing_id = created.data['id']
		self.client.force_authenticate(self.manager)
		updated = self.client.patch(
			reverse('marketplace:managed-listing-detail', kwargs={'pk': listing_id}),
			{'title': 'Updated courtyard home', 'monthly_rent_minor': 4600000},
			format='json',
		)
		self.assertEqual(updated.status_code, status.HTTP_200_OK)
		self.assertEqual(updated.data['title'], 'Updated courtyard home')
		self.assertEqual(updated.data['unit'], self.unit.pk)

		duplicate = self._create(user=self.manager)
		self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

		self._publish(listing_id, user=self.manager)
		self.client.force_authenticate(self.manager)
		draft = self.client.post(reverse('marketplace:managed-listing-unpublish', kwargs={'pk': listing_id}))
		self.assertEqual(draft.status_code, status.HTTP_200_OK)
		self.assertEqual(draft.data['status'], Listing.Status.DRAFT)
		self.assertFalse(draft.data['is_publicly_available'])
		self.client.force_authenticate(None)
		self.assertEqual(public_results(self.client.get(reverse('marketplace:public-listing-list'))), [])

	def test_disallowed_roles_and_other_organizations_cannot_manage(self):
		created = self._create()
		listing_id = created.data['id']
		manage_url = reverse('marketplace:managed-listing-detail', kwargs={'pk': listing_id})
		publish_url = reverse('marketplace:managed-listing-publish', kwargs={'pk': listing_id})

		for user in (self.accountant, self.caretaker, self.tenant_user):
			self.client.force_authenticate(user)
			self.assertEqual(self.client.get(reverse('marketplace:managed-listing-list')).status_code, status.HTTP_403_FORBIDDEN)
			self.assertEqual(self.client.patch(manage_url, {'title': 'Nope'}, format='json').status_code, status.HTTP_403_FORBIDDEN)
			self.assertEqual(self.client.post(publish_url).status_code, status.HTTP_403_FORBIDDEN)
			self.assertEqual(self.client.delete(manage_url).status_code, status.HTTP_403_FORBIDDEN)

		self.client.force_authenticate(None)
		self.assertEqual(self.client.get(reverse('marketplace:managed-listing-list')).status_code, status.HTTP_401_UNAUTHORIZED)

		self.client.force_authenticate(self.other)
		self.assertEqual(self.client.get(manage_url).status_code, status.HTTP_404_NOT_FOUND)
		self.assertEqual(self.client.patch(manage_url, {'title': 'Stolen'}, format='json').status_code, status.HTTP_404_NOT_FOUND)
		self.assertEqual(self.client.post(publish_url).status_code, status.HTTP_404_NOT_FOUND)
		self.assertEqual(self.client.delete(manage_url).status_code, status.HTTP_404_NOT_FOUND)
		stolen = self._create(unit=self.unit, user=self.other)
		self.assertEqual(stolen.status_code, status.HTTP_404_NOT_FOUND)
		self.assertTrue(Listing.objects.filter(pk=listing_id, title='Bright one-bedroom in Kilimani').exists())

	def test_photo_upload_serve_and_delete_do_not_publish_media_root(self):
		created = self._create()
		listing_id = created.data['id']
		self._publish(listing_id)
		upload_url = reverse('marketplace:managed-listing-photos', kwargs={'pk': listing_id})
		self.client.force_authenticate(self.owner)
		uploaded = self.client.post(upload_url, {'image': photo_file(), 'caption': 'Front door', 'is_primary': 'true'}, format='multipart')
		self.assertEqual(uploaded.status_code, status.HTTP_201_CREATED)
		photo = uploaded.data['photos'][0]
		self.assertTrue(photo['is_primary'])
		self.assertNotIn(MEDIA_ROOT, photo['url'])
		self.assertTrue(photo['url'].startswith(f'/api/v1/marketplace/manage/listings/{listing_id}/photos/'))

		rejected = self.client.post(upload_url, {'image': photo_file('notes.txt', 'text/plain', b'not-an-image')}, format='multipart')
		self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
		mismatch = self.client.post(upload_url, {'image': photo_file('room.jpg', 'image/png')}, format='multipart')
		self.assertEqual(mismatch.status_code, status.HTTP_400_BAD_REQUEST)
		spoofed = self.client.post(
			upload_url,
			{'image': photo_file('room.png', 'image/png', b'<html>not a PNG image</html>')},
			format='multipart',
		)
		self.assertEqual(spoofed.status_code, status.HTTP_400_BAD_REQUEST)

		stored = ListingPhoto.objects.get(pk=photo['id'])
		stored_path = Path(stored.image.path)
		self.assertTrue(stored_path.exists())
		media_url = f'/media/{stored.image.name}'
		self.client.force_authenticate(None)
		self.assertEqual(self.client.get(media_url).status_code, status.HTTP_404_NOT_FOUND)
		public = self.client.get(
			reverse('marketplace:public-listing-photo', kwargs={'pk': listing_id, 'photo_id': photo['id']}),
		)
		self.assertEqual(public.status_code, status.HTTP_200_OK)
		self.assertEqual(public['Content-Type'], 'image/png')
		self.assertEqual(public['X-Content-Type-Options'], 'nosniff')

		self.client.force_authenticate(self.other)
		manage_photo = reverse('marketplace:managed-listing-photo', kwargs={'pk': listing_id, 'photo_id': photo['id']})
		self.assertEqual(self.client.get(manage_photo).status_code, status.HTTP_404_NOT_FOUND)
		self.assertEqual(self.client.delete(manage_photo).status_code, status.HTTP_404_NOT_FOUND)

		self.client.force_authenticate(self.owner)
		deleted = self.client.delete(manage_photo)
		self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
		self.assertFalse(ListingPhoto.objects.filter(pk=photo['id']).exists())
		self.assertFalse(stored_path.exists())
		self.client.force_authenticate(None)
		self.assertEqual(
			self.client.get(reverse('marketplace:public-listing-photo', kwargs={'pk': listing_id, 'photo_id': photo['id']})).status_code,
			status.HTTP_404_NOT_FOUND,
		)

	def test_inquiry_is_public_and_visible_only_to_the_listing_organization(self):
		created = self._create()
		listing_id = created.data['id']
		self.client.force_authenticate(None)
		hidden = self.client.post(
			reverse('marketplace:inquiry-create'),
			{'listing': listing_id, 'name': 'Jane', 'email': 'jane@example.com', 'phone': '0700000000', 'message': 'Is it available?'},
			format='json',
		)
		self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)

		self._publish(listing_id)
		self.client.force_authenticate(None)
		created_inquiry = self.client.post(
			reverse('marketplace:inquiry-create'),
			{'listing': listing_id, 'name': 'Jane Wanjiku', 'email': 'jane@example.com', 'phone': '0700000000', 'message': 'Is the courtyard quiet?'},
			format='json',
		)
		self.assertEqual(created_inquiry.status_code, status.HTTP_201_CREATED)
		self.assertEqual(set(created_inquiry.data), {'id', 'created_at'})
		self.assertTrue(ListingInquiry.objects.filter(pk=created_inquiry.data['id'], listing_id=listing_id).exists())

		self.client.force_authenticate(self.owner)
		visible = self.client.get(reverse('marketplace:managed-listing-inquiries', kwargs={'pk': listing_id}))
		self.assertEqual(visible.status_code, status.HTTP_200_OK)
		self.assertEqual(visible.data[0]['email'], 'jane@example.com')

		self.client.force_authenticate(self.other)
		self.assertEqual(
			self.client.get(reverse('marketplace:managed-listing-inquiries', kwargs={'pk': listing_id})).status_code,
			status.HTTP_404_NOT_FOUND,
		)
		self.client.force_authenticate(self.tenant_user)
		self.assertEqual(
			self.client.get(reverse('marketplace:managed-listing-inquiries', kwargs={'pk': listing_id})).status_code,
			status.HTTP_403_FORBIDDEN,
		)

	def test_delete_listing_removes_photos(self):
		created = self._create()
		listing_id = created.data['id']
		self.client.force_authenticate(self.owner)
		uploaded = self.client.post(
			reverse('marketplace:managed-listing-photos', kwargs={'pk': listing_id}),
			{'image': photo_file()},
			format='multipart',
		)
		stored_path = Path(ListingPhoto.objects.get(pk=uploaded.data['photos'][0]['id']).image.path)
		deleted = self.client.delete(reverse('marketplace:managed-listing-detail', kwargs={'pk': listing_id}))
		self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
		self.assertFalse(Listing.objects.filter(pk=listing_id).exists())
		self.assertFalse(stored_path.exists())

	def test_non_kes_currency_is_rejected(self):
		response = self._create(currency='USD')
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_photo_count_and_size_limits_are_enforced(self):
		created = self._create()
		listing_id = created.data['id']
		upload_url = reverse('marketplace:managed-listing-photos', kwargs={'pk': listing_id})
		self.client.force_authenticate(self.owner)
		for index in range(12):
			uploaded = self.client.post(
				upload_url,
				{'image': photo_file(f'room-{index}.png')},
				format='multipart',
			)
			self.assertEqual(uploaded.status_code, status.HTTP_201_CREATED)
		thirteenth = self.client.post(
			upload_url,
			{'image': photo_file('room-12.png')},
			format='multipart',
		)
		self.assertEqual(thirteenth.status_code, status.HTTP_400_BAD_REQUEST)
		ListingPhoto.objects.filter(listing_id=listing_id).first().delete()
		too_large = self.client.post(
			upload_url,
			{'image': photo_file('huge.png', body=PNG + (b'0' * (8 * 1024 * 1024 + 1)))},
			format='multipart',
		)
		self.assertEqual(too_large.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('image', too_large.data)

	def test_amenity_wildcard_filters_are_rejected(self):
		created = self._create()
		self._publish(created.data['id'])
		self.client.force_authenticate(None)
		response = self.client.get(
			reverse('marketplace:public-listing-list'),
			{'amenity': 'Park%ing'},
		)
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_technician_cannot_manage_listings(self):
		User = get_user_model()
		technician = User.objects.create_user(username='mkt-technician', password='password')
		self._member(self.organization, technician, OrganizationMembership.Role.TECHNICIAN)
		created = self._create()
		self.client.force_authenticate(technician)
		self.assertEqual(
			self.client.get(reverse('marketplace:managed-listing-list')).status_code,
			status.HTTP_403_FORBIDDEN,
		)
		self.assertEqual(
			self.client.post(reverse('marketplace:managed-listing-publish', kwargs={'pk': created.data['id']})).status_code,
			status.HTTP_403_FORBIDDEN,
		)

	def test_tenant_service_request_persists_and_private_order_is_not_visible_to_property_owner(self):
		supplier = SupplierProfile.objects.create(organization=self.other_organization, created_by=self.other,
			business_name='Laundry Co', categories=['laundry'])
		listing = CommerceListing.objects.create(organization=self.other_organization, supplier=supplier,
			created_by=self.other, kind='SERVICE', category='laundry', title='Wash and fold',
			description='Laundry service', is_published=True, availability='AVAILABLE', price_minor=50000)
		tenant = Tenant.objects.get(user=self.tenant_user)
		Lease.objects.create(tenant=tenant, unit=self.unit, reference='L-COMMERCE', start_date=date(2026,1,1),
			monthly_rent_minor=4500000, status=Lease.Status.ACTIVE)
		self.client.force_authenticate(self.tenant_user)
		response = self.client.post(reverse('marketplace:commerce-order-list'), {'listing': listing.pk, 'quantity': '1'}, format='json')
		self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
		order = CommerceOrder.objects.get(pk=response.data['id'])
		self.assertEqual(order.requested_by, self.tenant_user)
		self.assertEqual(response.data['payment_status'], 'NOT_INTEGRATED')
		self.client.force_authenticate(self.owner)
		self.assertEqual(self.client.get(reverse('marketplace:commerce-order-list')).data, [])
		forbidden = self.client.patch(reverse('marketplace:commerce-order-detail', kwargs={'pk': order.pk}), {'status': 'ACCEPTED'}, format='json')
		self.assertEqual(forbidden.status_code, status.HTTP_404_NOT_FOUND)
		self.client.force_authenticate(self.tenant_user)
		self.assertEqual(len(self.client.get(reverse('marketplace:commerce-order-list')).data), 1)
		self.client.force_authenticate(self.other)
		accepted = self.client.patch(reverse('marketplace:commerce-order-detail', kwargs={'pk': order.pk}), {'status': 'ACCEPTED'}, format='json')
		self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.data)
		self.assertEqual(CommerceOrder.objects.get(pk=order.pk).status, 'ACCEPTED')
		self.assertEqual(AuditLog.objects.filter(object_type='CommerceOrder', object_id=str(order.pk)).count(), 2)

	def test_deactivated_listing_organization_blocks_new_orders_and_hides_old_orders(self):
		supplier = SupplierProfile.objects.create(
			organization=self.other_organization,
			created_by=self.other,
			business_name='Closed Laundry',
			categories=['laundry'],
		)
		listing = CommerceListing.objects.create(
			organization=self.other_organization,
			supplier=supplier,
			created_by=self.other,
			kind='SERVICE',
			category='laundry',
			title='Closed laundry service',
			description='No longer accepting requests',
			is_published=True,
			availability='AVAILABLE',
			price_minor=50000,
		)
		tenant = Tenant.objects.get(user=self.tenant_user)
		Lease.objects.create(
			tenant=tenant,
			unit=self.unit,
			reference='L-COMMERCE-DEACTIVATED',
			start_date=date(2026, 1, 1),
			monthly_rent_minor=4500000,
			status=Lease.Status.ACTIVE,
		)
		self.client.force_authenticate(self.tenant_user)
		created = self.client.post(
			reverse('marketplace:commerce-order-list'),
			{'listing': listing.pk, 'quantity': '1'},
			format='json',
		)
		self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)

		self.other_organization.is_active = False
		self.other_organization.save(update_fields=('is_active', 'updated_at'))
		old_orders = self.client.get(reverse('marketplace:commerce-order-list'))
		new_order = self.client.post(
			reverse('marketplace:commerce-order-list'),
			{'listing': listing.pk, 'quantity': '1'},
			format='json',
		)

		self.assertEqual(old_orders.status_code, status.HTTP_200_OK)
		self.assertEqual(old_orders.data, [])
		self.assertEqual(new_order.status_code, status.HTTP_400_BAD_REQUEST)

		self.other_organization.is_active = True
		self.other_organization.save(update_fields=('is_active', 'updated_at'))
		self.organization.is_active = False
		self.organization.save(update_fields=('is_active', 'updated_at'))
		inactive_tenant_org_order = self.client.post(
			reverse('marketplace:commerce-order-list'),
			{'listing': listing.pk, 'quantity': '1'},
			format='json',
		)
		self.assertEqual(inactive_tenant_org_order.status_code, status.HTTP_403_FORBIDDEN)

	def test_lease_start_today_in_nairobi_authorizes_marketplace_request_before_utc_midnight(self):
		supplier = SupplierProfile.objects.create(
			organization=self.other_organization,
			created_by=self.other,
			business_name='Nairobi Laundry',
			categories=['laundry'],
		)
		listing = CommerceListing.objects.create(
			organization=self.other_organization,
			supplier=supplier,
			created_by=self.other,
			kind='SERVICE',
			category='laundry',
			title='Wash and fold',
			description='Laundry service',
			is_published=True,
			availability='AVAILABLE',
			price_minor=50000,
		)
		tenant = Tenant.objects.get(user=self.tenant_user)
		Lease.objects.create(
			tenant=tenant,
			unit=self.unit,
			reference='L-NAIROBI-START',
			start_date=date(2026, 10, 15),
			monthly_rent_minor=4500000,
			status=Lease.Status.ACTIVE,
		)
		self.client.force_authenticate(self.tenant_user)
		instant = datetime(2026, 10, 14, 22, 30, tzinfo=datetime_timezone.utc)

		with patch('django.utils.timezone.now', return_value=instant):
			response = self.client.post(
				reverse('marketplace:commerce-order-list'),
				{'listing': listing.pk, 'quantity': '1'},
				format='json',
			)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

	def test_public_listing_reappears_only_after_inclusive_lease_day_and_expiry(self):
		created = self._create()
		self.assertEqual(self._publish(created.data['id']).status_code, status.HTTP_200_OK)
		tenant = Tenant.objects.get(user=self.tenant_user)
		lease = Lease.objects.create(
			tenant=tenant,
			unit=self.unit,
			reference='L-MARKET-END-DAY',
			start_date=date(2026, 10, 1),
			monthly_rent_minor=4500000,
		)
		self.client.force_authenticate(self.owner)
		activated = self.client.post(f'/api/v1/leases/{lease.pk}/activate/')
		self.assertEqual(activated.status_code, status.HTTP_200_OK, activated.data)

		final_day_instant = datetime(2026, 10, 14, 22, 30, tzinfo=datetime_timezone.utc)
		with patch('django.utils.timezone.now', return_value=final_day_instant):
			termination = self.client.post(
				f'/api/v1/leases/{lease.pk}/terminate/',
				{'end_date': '2026-10-15', 'reason': 'Final inclusive day'},
				format='json',
			)
		self.assertEqual(termination.status_code, status.HTTP_200_OK, termination.data)
		self.assertEqual(termination.data['status'], Lease.Status.ACTIVE)
		self.unit.refresh_from_db()
		self.assertEqual(self.unit.status, Unit.Status.OCCUPIED)
		self.client.force_authenticate(None)
		self.assertEqual(public_results(self.client.get(reverse('marketplace:public-listing-list'))), [])

		after_final_day_instant = datetime(2026, 10, 15, 21, 30, tzinfo=datetime_timezone.utc)
		self.client.force_authenticate(self.owner)
		with patch('django.utils.timezone.now', return_value=after_final_day_instant):
			finalized = self.client.post(f'/api/v1/leases/{lease.pk}/expire/')
		self.assertEqual(finalized.status_code, status.HTTP_200_OK, finalized.data)
		self.unit.refresh_from_db()
		self.assertEqual(self.unit.status, Unit.Status.AVAILABLE)
		self.client.force_authenticate(None)
		self.assertEqual(len(public_results(self.client.get(reverse('marketplace:public-listing-list')))), 1)
