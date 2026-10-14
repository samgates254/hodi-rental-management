from datetime import date, datetime, timezone as datetime_timezone
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.leases.models import Lease
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant
from common.rental_dates import rental_business_date

from .models import MaintenanceIssue, MaintenanceIssueUpdate, MaintenanceRequest, WorkOrder


class MaintenanceIssueApiTests(TestCase):
	def setUp(self):
		self.media_directory = TemporaryDirectory()
		self.enterContext(override_settings(MEDIA_ROOT=self.media_directory.name))
		self.addCleanup(self.media_directory.cleanup)
		user_model = get_user_model()
		self.tenant_user = user_model.objects.create_user(username='tenant', password='secret')
		self.caretaker = user_model.objects.create_user(username='caretaker', password='secret')
		self.other_user = user_model.objects.create_user(username='other', password='secret')
		self.organization = Organization.objects.create(name='First Homes')
		self.other_organization = Organization.objects.create(name='Second Homes')
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.caretaker,
			role=OrganizationMembership.Role.CARETAKER,
		)
		OrganizationMembership.objects.create(
			organization=self.other_organization,
			user=self.other_user,
			role=OrganizationMembership.Role.TECHNICIAN,
		)
		self.tenant = Tenant.objects.create(
			user=self.tenant_user,
			organization=self.organization,
			first_name='Ada',
			last_name='Tenant',
			phone_number='0700000000',
		)
		self.unit = self.create_unit(self.organization, 'A-1')
		self.lease = Lease.objects.create(
			tenant=self.tenant,
			unit=self.unit,
			reference='LEASE-A',
			start_date=date(2026, 1, 1),
			monthly_rent_minor=100000,
		)
		self.client = APIClient()

	def create_unit(self, organization, name):
		property_record = Property.objects.create(organization=organization, name=f'{organization.name} property')
		building = Building.objects.create(property=property_record, name='Block A')
		return Unit.objects.create(building=building, name=name)

	def issue_payload(self, unit=None):
		return {
			'unit': (unit or self.unit).pk,
			'title': 'Leaking kitchen tap',
			'category': 'PLUMBING',
			'priority': 'HIGH',
			'description': 'The tap is leaking continuously.',
		}

	def test_linked_tenant_can_create_issue_and_creation_is_recorded(self):
		self.lease.status = Lease.Status.ACTIVE
		self.lease.start_date = rental_business_date()
		self.lease.save(update_fields=('status', 'start_date', 'updated_at'))
		self.client.force_authenticate(self.tenant_user)

		response = self.client.post('/api/v1/maintenance/issues/', self.issue_payload(), format='json')

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		issue = MaintenanceIssue.objects.get()
		self.assertEqual(issue.tenant, self.tenant)
		self.assertEqual(issue.status, MaintenanceIssue.Status.OPEN)
		self.assertEqual(issue.updates.get().author, self.tenant_user)
		self.assertIsNotNone(issue.operational_request_id)
		self.assertEqual(issue.operational_request.title, issue.title)
		self.assertEqual(issue.operational_request.tenant_id, issue.tenant_id)
		self.assertTrue(WorkOrder.objects.filter(request=issue.operational_request).exists())

	def test_tenant_issue_is_created_on_their_active_lease_unit(self):
		self.lease.status = Lease.Status.ACTIVE
		self.lease.start_date = rental_business_date()
		self.lease.save(update_fields=('status', 'start_date', 'updated_at'))
		self.client.force_authenticate(self.tenant_user)
		payload = self.issue_payload()
		payload.pop('unit')

		response = self.client.post('/api/v1/maintenance/issues/', payload, format='json')

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data['unit'], self.unit.pk)

	def test_lease_start_today_in_nairobi_authorizes_maintenance(self):
		self.lease.status = Lease.Status.ACTIVE
		self.lease.start_date = date(2026, 10, 15)
		self.lease.save(update_fields=('status', 'start_date', 'updated_at'))
		self.client.force_authenticate(self.tenant_user)
		instant_before_utc_midnight = datetime(
			2026, 10, 14, 22, 30, tzinfo=datetime_timezone.utc,
		)

		with patch('django.utils.timezone.now', return_value=instant_before_utc_midnight):
			response = self.client.post('/api/v1/maintenance/issues/', self.issue_payload(), format='json')

		self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
		self.assertEqual(MaintenanceIssue.objects.get().tenant, self.tenant)

	def test_tenant_remains_authorized_through_the_inclusive_lease_end_day(self):
		self.lease.status = Lease.Status.ACTIVE
		self.lease.start_date = date(2026, 10, 1)
		self.lease.end_date = date(2026, 10, 15)
		self.lease.save(update_fields=('status', 'start_date', 'end_date', 'updated_at'))
		self.client.force_authenticate(self.tenant_user)
		instant_before_utc_midnight = datetime(
			2026, 10, 14, 22, 30, tzinfo=datetime_timezone.utc,
		)

		with patch('django.utils.timezone.now', return_value=instant_before_utc_midnight):
			response = self.client.post('/api/v1/maintenance/issues/', self.issue_payload(), format='json')

		self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

	def test_linked_maintenance_cannot_reopen_after_resolution(self):
		self.lease.status = Lease.Status.ACTIVE
		self.lease.start_date = rental_business_date()
		self.lease.save(update_fields=('status', 'start_date', 'updated_at'))
		self.client.force_authenticate(self.tenant_user)
		created = self.client.post('/api/v1/maintenance/issues/', self.issue_payload(), format='json')
		self.client.force_authenticate(self.caretaker)
		resolved = self.client.post(
			f"/api/v1/maintenance/issues/{created.data['id']}/updates/",
			{'status': MaintenanceIssue.Status.RESOLVED, 'note': 'Repair verified.'},
			format='json',
		)
		self.assertEqual(resolved.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertEqual(MaintenanceRequest.objects.get(pk=created.data['operational_request_id']).status, MaintenanceRequest.Status.OPEN)
		reopened = self.client.post(
			f"/api/v1/maintenance/issues/{created.data['id']}/updates/",
			{'status': MaintenanceIssue.Status.IN_PROGRESS},
			format='json',
		)
		self.assertEqual(reopened.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertEqual(created.data['operational_request_id'], MaintenanceIssue.objects.get().operational_request_id)

	def test_tenant_can_submit_photos_and_videos_that_are_visible_to_caretaker(self):
		self.lease.status = Lease.Status.ACTIVE
		self.lease.start_date = rental_business_date()
		self.lease.save(update_fields=('status', 'start_date', 'updated_at'))
		self.client.force_authenticate(self.tenant_user)

		response = self.client.post(
			'/api/v1/maintenance/issues/',
			{
				'title': 'Water leak',
				'category': 'PLUMBING',
				'priority': 'HIGH',
				'description': 'The pipe is leaking.',
				'attachments': [
					SimpleUploadedFile('leak.jpg', b'photo-content', content_type='image/jpeg'),
					SimpleUploadedFile('leak.mp4', b'video-content', content_type='video/mp4'),
				],
			},
			format='multipart',
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		attachments = response.data['attachments']
		self.assertEqual([item['media_type'] for item in attachments], ['IMAGE', 'VIDEO'])
		self.client.force_authenticate(self.caretaker)
		caretaker_list = self.client.get('/api/v1/maintenance/issues/')
		self.assertEqual(caretaker_list.data[0]['attachments'], attachments)
		attachment_response = self.client.get(attachments[0]['url'])
		self.assertEqual(attachment_response.status_code, status.HTTP_200_OK)
		self.assertEqual(attachment_response['Content-Type'], 'image/jpeg')

	def test_tenant_cannot_upload_unsupported_attachment_types(self):
		self.lease.status = Lease.Status.ACTIVE
		self.lease.start_date = rental_business_date()
		self.lease.save(update_fields=('status', 'start_date', 'updated_at'))
		self.client.force_authenticate(self.tenant_user)

		response = self.client.post(
			'/api/v1/maintenance/issues/',
			{
				'title': 'Unexpected file',
				'category': 'OTHER',
				'description': 'Testing an unsupported attachment.',
				'attachments': [
					SimpleUploadedFile('script.svg', b'<svg/>', content_type='image/svg+xml'),
				],
			},
			format='multipart',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertFalse(MaintenanceIssue.objects.exists())

	def test_attachment_download_is_limited_to_issue_access(self):
		issue = MaintenanceIssue.objects.create(
			tenant=self.tenant,
			unit=self.unit,
			title='Broken light',
			category='ELECTRICAL',
			description='No light in the hallway.',
		)
		attachment = issue.attachments.create(
			file=SimpleUploadedFile('light.png', b'image-content', content_type='image/png'),
			file_name='light.png',
			content_type='image/png',
			media_type='IMAGE',
		)
		self.client.force_authenticate(self.other_user)

		response = self.client.get(
			f'/api/v1/maintenance/issues/{issue.pk}/attachments/{attachment.pk}/',
		)

		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

	def test_unlinked_user_cannot_create_an_issue(self):
		unlinked_user = get_user_model().objects.create_user(username='unlinked', password='secret')
		self.client.force_authenticate(unlinked_user)

		response = self.client.post('/api/v1/maintenance/issues/', self.issue_payload(), format='json')

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
		self.assertFalse(MaintenanceIssue.objects.exists())

	def test_tenant_cannot_create_issue_for_unit_outside_their_lease(self):
		other_unit = self.create_unit(self.other_organization, 'B-1')
		self.client.force_authenticate(self.tenant_user)

		response = self.client.post(
			'/api/v1/maintenance/issues/',
			self.issue_payload(other_unit),
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertFalse(MaintenanceIssue.objects.exists())

	def test_caretaker_lists_only_membership_issues_and_can_add_status_history(self):
		issue = MaintenanceIssue.objects.create(
			tenant=self.tenant,
			unit=self.unit,
			title='Broken light',
			category='ELECTRICAL',
			description='No light in the hallway.',
		)
		other_tenant = Tenant.objects.create(
			organization=self.other_organization,
			first_name='Other',
			last_name='Tenant',
			phone_number='0711111111',
		)
		other_unit = self.create_unit(self.other_organization, 'B-1')
		MaintenanceIssue.objects.create(
			tenant=other_tenant,
			unit=other_unit,
			title='Hidden issue',
			category='OTHER',
			description='Not in this organization.',
		)
		self.client.force_authenticate(self.caretaker)

		response = self.client.get('/api/v1/maintenance/issues/')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual([item['id'] for item in response.data], [issue.pk])
		listed_issue = response.data[0]
		self.assertEqual(listed_issue['organization'], self.organization.pk)
		self.assertEqual(listed_issue['tenant_name'], 'Ada Tenant')
		self.assertEqual(listed_issue['unit_name'], 'A-1')
		self.assertEqual(listed_issue['property_name'], 'First Homes property')

		update_response = self.client.post(
			f'/api/v1/maintenance/issues/{issue.pk}/updates/',
			{'status': 'IN_PROGRESS', 'note': 'Assigned an electrician.'},
			format='json',
		)
		self.assertEqual(update_response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(update_response.data['author_name'], 'caretaker')
		second_update_response = self.client.post(
			f'/api/v1/maintenance/issues/{issue.pk}/updates/',
			{'status': 'RESOLVED', 'note': 'Replaced the bulb.'},
			format='json',
		)
		self.assertEqual(second_update_response.status_code, status.HTTP_201_CREATED)
		issue.refresh_from_db()
		self.assertEqual(issue.status, MaintenanceIssue.Status.RESOLVED)
		self.assertIsNotNone(issue.resolved_at)
		self.assertEqual(MaintenanceIssueUpdate.objects.filter(issue=issue).count(), 2)
		self.assertEqual(
			[update['note'] for update in second_update_response.data and self.client.get(
				'/api/v1/maintenance/issues/',
			).data[0]['updates']],
			['Assigned an electrician.', 'Replaced the bulb.'],
		)
		self.assertTrue(all(
			update['author_name'] == 'caretaker'
			for update in self.client.get('/api/v1/maintenance/issues/').data[0]['updates']
		))

	def test_caretaker_can_filter_shared_issues_by_selected_organization(self):
		OrganizationMembership.objects.create(
			organization=self.other_organization,
			user=self.caretaker,
			role=OrganizationMembership.Role.CARETAKER,
		)
		other_tenant = Tenant.objects.create(
			organization=self.other_organization,
			first_name='Other',
			last_name='Tenant',
			phone_number='0711111111',
		)
		other_unit = self.create_unit(self.other_organization, 'B-1')
		other_issue = MaintenanceIssue.objects.create(
			tenant=other_tenant,
			unit=other_unit,
			title='Broken gate',
			category='SECURITY',
			description='The gate does not lock.',
		)
		self.client.force_authenticate(self.caretaker)

		response = self.client.get(
			'/api/v1/maintenance/issues/',
			{'organization': self.other_organization.pk},
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual([item['id'] for item in response.data], [other_issue.pk])

	def test_unrelated_member_cannot_access_an_issue(self):
		issue = MaintenanceIssue.objects.create(
			tenant=self.tenant,
			unit=self.unit,
			title='Broken light',
			category='ELECTRICAL',
			description='No light in the hallway.',
		)
		self.client.force_authenticate(self.other_user)

		response = self.client.get(f'/api/v1/maintenance/issues/{issue.pk}/')

		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

	def test_tenant_cannot_update_issue_status_or_history(self):
		issue = MaintenanceIssue.objects.create(
			tenant=self.tenant,
			unit=self.unit,
			title='Broken light',
			category='ELECTRICAL',
			description='No light in the hallway.',
		)
		self.client.force_authenticate(self.tenant_user)

		response = self.client.post(
			f'/api/v1/maintenance/issues/{issue.pk}/updates/',
			{'status': 'RESOLVED'},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
		issue.refresh_from_db()
		self.assertEqual(issue.status, MaintenanceIssue.Status.OPEN)
		self.assertFalse(issue.updates.exists())

	def test_tenant_can_list_own_issue_and_add_a_note_shared_with_caretaker(self):
		issue = MaintenanceIssue.objects.create(
			tenant=self.tenant,
			unit=self.unit,
			title='Broken light',
			category='ELECTRICAL',
			description='No light in the hallway.',
		)
		self.client.force_authenticate(self.tenant_user)

		list_response = self.client.get('/api/v1/maintenance/issues/')
		comment_response = self.client.post(
			f'/api/v1/maintenance/issues/{issue.pk}/updates/',
			{'note': 'The light is still not working.'},
			format='json',
		)

		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual([item['id'] for item in list_response.data], [issue.pk])
		self.assertEqual(comment_response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(comment_response.data['note'], 'The light is still not working.')
		self.assertEqual(comment_response.data['author_name'], 'tenant')
		issue.refresh_from_db()
		self.assertEqual(issue.status, MaintenanceIssue.Status.OPEN)
