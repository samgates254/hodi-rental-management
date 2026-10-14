from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import AccountProfile
from apps.marketplace.models import (
	AgentProfile,
	AgentUnitAuthorization,
	Listing,
	ListingInquiry,
	ViewingRequest,
)
from apps.notifications.models import Notification
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.marketplace.services import publish_listing as publish_listing_service


def public_results(response):
	return response.data.get('results', []) if isinstance(response.data, dict) else response.data


@override_settings(
	EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
	DEFAULT_FROM_EMAIL='accounts@example.com',
)
class AgentMarketplaceWorkflowTests(APITestCase):
	def setUp(self):
		User = get_user_model()
		self.owner = User.objects.create_user(username='agent-owner', email='owner@example.com', password='SafePass123!')
		self.manager = User.objects.create_user(username='agent-manager', email='manager@example.com', password='SafePass123!')
		self.agent_user = User.objects.create_user(username='listing-agent', email='agent@example.com', password='SafePass123!')
		self.other_agent_user = User.objects.create_user(username='other-agent', email='other-agent@example.com', password='SafePass123!')
		self.staff = User.objects.create_user(username='agent-reviewer', email='reviewer@example.com', password='SafePass123!', is_staff=True)
		self.organization = Organization.objects.create(name='Agent Test Homes')
		self.other_organization = Organization.objects.create(name='Other Agent Homes')
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.owner,
			role=OrganizationMembership.Role.OWNER,
		)
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.manager,
			role=OrganizationMembership.Role.PROPERTY_MANAGER,
		)
		OrganizationMembership.objects.create(
			organization=self.other_organization,
			user=self.owner,
			role=OrganizationMembership.Role.OWNER,
			is_active=False,
		)
		for user in (self.agent_user, self.other_agent_user):
			AccountProfile.objects.create(
				user=user,
				account_type=AccountProfile.AccountType.PROPERTY_AGENT,
				email_verified_at=timezone.now(),
			)
		self.agent = AgentProfile.objects.create(
			user=self.agent_user,
			display_name='Mina Agent',
			public_email=self.agent_user.email,
		)
		self.other_agent = AgentProfile.objects.create(
			user=self.other_agent_user,
			display_name='Other Agent',
			public_email=self.other_agent_user.email,
		)
		property_record = Property.objects.create(
			organization=self.organization,
			name='Agent Test Court',
			city='Nairobi',
		)
		building = Building.objects.create(property=property_record, name='A')
		self.unit = Unit.objects.create(building=building, name='A-1', bedrooms=1)
		self.listing_payload = {
			'unit': self.unit.pk,
			'title': 'One bedroom near town',
			'description': 'Owner-authorized listing.',
			'monthly_rent_minor': 4500000,
			'bedrooms': 1,
			'bathrooms': 1,
			'area': 'Upper Hill',
			'city': 'Nairobi',
		}

	def _grant(self, user=None, **overrides):
		payload = {
			'organization': self.organization.pk,
			'unit': self.unit.pk,
			'agent_email': self.agent_user.email,
			'attest_authority': True,
			'authority_reference': 'MANAGEMENT-AGREEMENT-01',
		}
		payload.update(overrides)
		self.client.force_authenticate(user or self.owner)
		return self.client.post(reverse('marketplace:agent-authorization-list-create'), payload, format='json')

	def _create_agent_draft(self):
		self.client.force_authenticate(self.agent_user)
		return self.client.post(
			reverse('marketplace:agent-listing-list'),
			self.listing_payload,
			format='json',
		)

	def test_signup_creates_independent_unverified_agent_without_owner_privileges(self):
		response = self.client.post(reverse('accounts:signup'), {
			'account_type': AccountProfile.AccountType.PROPERTY_AGENT,
			'username': 'new-property-agent',
			'email': 'new-agent@example.com',
			'first_name': 'Nia',
			'last_name': 'Kamau',
			'phone_number': '+254700000123',
			'password': 'SafePass123!long',
			'password_confirm': 'SafePass123!long',
		}, format='json')
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		user = get_user_model().objects.get(username='new-property-agent')
		self.assertEqual(user.account_profile.account_type, AccountProfile.AccountType.PROPERTY_AGENT)
		self.assertEqual(user.agent_profile.verification_status, AgentProfile.VerificationStatus.UNVERIFIED)
		self.assertFalse(user.organization_memberships.exists())
		self.assertFalse(hasattr(user, 'tenant_record'))
		self.assertEqual(response.data['agent_verification_status'], AgentProfile.VerificationStatus.UNVERIFIED)
		self.assertTrue(response.data['email_verification_required'])
		self.assertIsNone(response.data['token'])
		self.assertEqual(len(mail.outbox), 1)
		self.assertIn('/verify-email#token=', mail.outbox[0].body)
		self.assertFalse(Token.objects.filter(user=user).exists())

	def test_unverified_agent_cannot_be_authorized_or_access_workspace(self):
		account = self.agent_user.account_profile
		account.email_verified_at = None
		account.save(update_fields=('email_verified_at', 'updated_at'))

		grant = self._grant()
		self.assertEqual(grant.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertFalse(AgentUnitAuthorization.objects.filter(agent=self.agent).exists())

		self.client.force_authenticate(self.agent_user)
		workspace = self.client.get(reverse('marketplace:agent-profile'))
		self.assertEqual(workspace.status_code, status.HTTP_403_FORBIDDEN)

	def test_owner_authorization_is_required_and_manager_cannot_grant_it(self):
		unauthorized = self._create_agent_draft()
		self.assertEqual(unauthorized.status_code, status.HTTP_404_NOT_FOUND)
		self.assertFalse(Listing.objects.exists())

		manager_grant = self._grant(user=self.manager)
		self.assertEqual(manager_grant.status_code, status.HTTP_403_FORBIDDEN)

		wrong_organization = self._grant(organization=self.other_organization.pk)
		self.assertEqual(wrong_organization.status_code, status.HTTP_403_FORBIDDEN)

		missing_attestation = self._grant(attest_authority=False)
		self.assertEqual(missing_attestation.status_code, status.HTTP_400_BAD_REQUEST)

		granted = self._grant()
		self.assertEqual(granted.status_code, status.HTTP_201_CREATED)
		self.assertEqual(granted.data['status'], AgentUnitAuthorization.Status.ACTIVE)
		self.assertEqual(granted.data['authority_reference'], 'MANAGEMENT-AGREEMENT-01')
		self.assertEqual(granted.data['agent'], self.agent.pk)

	def test_agent_can_draft_but_requires_staff_verification_to_publish(self):
		self._grant()
		created = self._create_agent_draft()
		self.assertEqual(created.status_code, status.HTTP_201_CREATED)
		listing = Listing.objects.get(pk=created.data['id'])
		self.assertEqual(listing.created_by, self.agent_user)
		self.assertEqual(listing.agent_profile, self.agent)
		self.assertEqual(listing.status, Listing.Status.DRAFT)

		publish_url = reverse('marketplace:agent-listing-publish', kwargs={'pk': listing.pk})
		denied = self.client.post(publish_url)
		self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
		self.assertEqual(listing.status, Listing.Status.DRAFT)

		self.client.force_authenticate(self.staff)
		moderate = self.client.post(reverse(
			'marketplace:agent-profile-moderate', kwargs={'profile_id': self.agent.pk},
		), {'verification_status': AgentProfile.VerificationStatus.VERIFIED}, format='json')
		self.assertEqual(moderate.status_code, status.HTTP_200_OK)

		self.client.force_authenticate(self.agent_user)
		published = self.client.post(publish_url)
		self.assertEqual(published.status_code, status.HTTP_200_OK, published.data)
		self.assertEqual(published.data['status'], Listing.Status.PUBLISHED)
		public_rows = self.client.get(reverse('marketplace:public-listing-list'))
		self.assertEqual(len(public_results(public_rows)), 1)

	def test_agent_and_listing_data_are_isolated_and_revocation_unpublishes(self):
		self._grant()
		created = self._create_agent_draft()
		listing = Listing.objects.get(pk=created.data['id'])
		self.agent.verification_status = AgentProfile.VerificationStatus.VERIFIED
		self.agent.save(update_fields=('verification_status',))
		self.client.force_authenticate(self.agent_user)
		self.client.post(reverse('marketplace:agent-listing-publish', kwargs={'pk': listing.pk}))

		self.client.force_authenticate(self.other_agent_user)
		self.assertEqual(
			self.client.get(reverse('marketplace:agent-listing-detail', kwargs={'pk': listing.pk})).status_code,
			status.HTTP_404_NOT_FOUND,
		)
		self.assertEqual(self.client.get(reverse('marketplace:agent-inquiry-list')).data, [])

		self.client.force_authenticate(self.owner)
		authorization = AgentUnitAuthorization.objects.get(unit=self.unit, status=AgentUnitAuthorization.Status.ACTIVE)
		revoked = self.client.delete(reverse(
			'marketplace:agent-authorization-detail', kwargs={'authorization_id': authorization.pk},
		))
		self.assertEqual(revoked.status_code, status.HTTP_200_OK)
		listing.refresh_from_db()
		self.assertEqual(listing.status, Listing.Status.PAUSED)
		self.assertIsNone(listing.agent_profile_id)
		self.assertEqual(public_results(self.client.get(reverse('marketplace:public-listing-list'))), [])

		self.client.force_authenticate(self.agent_user)
		denied = self.client.post(reverse('marketplace:agent-listing-publish', kwargs={'pk': listing.pk}))
		self.assertEqual(denied.status_code, status.HTTP_404_NOT_FOUND)
		self.assertEqual(self.client.get(reverse('marketplace:agent-inquiry-list')).data, [])

	def test_revocation_between_agent_check_and_publish_cannot_republish_unassigned_listing(self):
		self._grant()
		created = self._create_agent_draft()
		listing = Listing.objects.get(pk=created.data['id'])
		self.agent.verification_status = AgentProfile.VerificationStatus.VERIFIED
		self.agent.save(update_fields=('verification_status',))
		self.client.force_authenticate(self.agent_user)
		published = self.client.post(reverse('marketplace:agent-listing-publish', kwargs={'pk': listing.pk}))
		self.assertEqual(published.status_code, status.HTTP_200_OK)
		authorization = AgentUnitAuthorization.objects.get(unit=self.unit, status=AgentUnitAuthorization.Status.ACTIVE)
		owner_client = self.client.__class__()
		owner_client.force_authenticate(self.owner)

		def revoke_then_publish(stale_listing, **kwargs):
			revoked = owner_client.delete(reverse(
				'marketplace:agent-authorization-detail', kwargs={'authorization_id': authorization.pk},
			))
			self.assertEqual(revoked.status_code, status.HTTP_200_OK)
			return publish_listing_service(stale_listing, **kwargs)

		self.client.force_authenticate(self.agent_user)
		with patch('apps.marketplace.views.publish_listing', side_effect=revoke_then_publish):
			response = self.client.post(reverse('marketplace:agent-listing-publish', kwargs={'pk': listing.pk}))

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		listing.refresh_from_db()
		self.assertEqual(listing.status, Listing.Status.PAUSED)
		self.assertIsNone(listing.agent_profile_id)
		self.assertEqual(public_results(self.client.get(reverse('marketplace:public-listing-list'))), [])

	def test_reassigned_listing_and_enquiries_are_private_from_previous_agent(self):
		self._grant()
		created = self._create_agent_draft()
		listing = Listing.objects.get(pk=created.data['id'])
		self.agent.verification_status = AgentProfile.VerificationStatus.VERIFIED
		self.agent.save(update_fields=('verification_status',))
		self.client.force_authenticate(self.agent_user)
		self.client.post(reverse('marketplace:agent-listing-publish', kwargs={'pk': listing.pk}))

		self.client.force_authenticate(self.owner)
		authorization = AgentUnitAuthorization.objects.get(
			unit=self.unit,
			status=AgentUnitAuthorization.Status.ACTIVE,
		)
		self.client.delete(reverse(
			'marketplace:agent-authorization-detail', kwargs={'authorization_id': authorization.pk},
		))
		self._grant(agent_email=self.other_agent_user.email)
		listing.refresh_from_db()
		self.assertEqual(listing.agent_profile, self.other_agent)
		self.other_agent.verification_status = AgentProfile.VerificationStatus.VERIFIED
		self.other_agent.save(update_fields=('verification_status',))
		self.client.force_authenticate(self.other_agent_user)
		self.client.post(reverse('marketplace:agent-listing-publish', kwargs={'pk': listing.pk}))

		self.client.force_authenticate(None)
		inquiry = self.client.post(reverse('marketplace:inquiry-create'), {
			'listing': str(listing.pk),
			'name': 'New prospective tenant',
			'email': 'new-tenant@example.com',
			'message': 'Please contact me about this home.',
		}, format='json')
		self.assertEqual(inquiry.status_code, status.HTTP_201_CREATED)
		self.assertFalse(Notification.objects.filter(user=self.agent_user).exists())
		self.assertTrue(Notification.objects.filter(user=self.other_agent_user).exists())

		self.client.force_authenticate(self.agent_user)
		for action_name in ('pause', 'archive'):
			response = self.client.post(reverse(
				f'marketplace:agent-listing-{action_name}', kwargs={'pk': listing.pk},
			))
			self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
		self.assertEqual(self.client.get(reverse('marketplace:agent-listing-list')).data, [])
		listing.refresh_from_db()
		self.assertEqual(listing.agent_profile, self.other_agent)
		self.assertEqual(listing.status, Listing.Status.PUBLISHED)

	def test_public_inquiry_and_viewing_are_validated_and_agent_can_manage_them(self):
		self._grant()
		created = self._create_agent_draft()
		listing = Listing.objects.get(pk=created.data['id'])
		self.agent.verification_status = AgentProfile.VerificationStatus.VERIFIED
		self.agent.save(update_fields=('verification_status',))
		self.client.force_authenticate(self.agent_user)
		self.client.post(reverse('marketplace:agent-listing-publish', kwargs={'pk': listing.pk}))
		self.client.force_authenticate(None)

		inquiry_url = reverse('marketplace:inquiry-create')
		past = self.client.post(inquiry_url, {
			'listing': str(listing.pk),
			'name': 'Potential tenant',
			'email': 'tenant@example.com',
			'message': 'Can I view the unit?',
			'viewing_requested_for': (timezone.now() - timedelta(days=1)).isoformat(),
		}, format='json')
		self.assertEqual(past.status_code, status.HTTP_400_BAD_REQUEST)

		future = self.client.post(inquiry_url, {
			'listing': str(listing.pk),
			'name': 'Potential tenant',
			'email': 'tenant@example.com',
			'phone': '+254700000111',
			'message': 'Can I view the unit?',
			'viewing_requested_for': (timezone.now() + timedelta(days=2)).isoformat(),
		}, format='json')
		self.assertEqual(future.status_code, status.HTTP_201_CREATED)
		self.assertEqual(ListingInquiry.objects.get(pk=future.data['id']).status, ListingInquiry.Status.NEW)
		self.assertTrue(ViewingRequest.objects.filter(inquiry_id=future.data['id']).exists())

		self.client.force_authenticate(self.agent_user)
		inquiries = self.client.get(reverse('marketplace:agent-inquiry-list'))
		self.assertEqual(inquiries.status_code, status.HTTP_200_OK)
		self.assertEqual(len(inquiries.data), 1)
		self.assertEqual(inquiries.data[0]['name'], 'Potential tenant')
		self.assertEqual(inquiries.data[0]['viewing_request']['status'], ViewingRequest.Status.REQUESTED)
		updated = self.client.patch(reverse('marketplace:agent-inquiry-status-update', kwargs={'pk': future.data['id']}), {
			'status': ListingInquiry.Status.CONTACTED,
		}, format='json')
		self.assertEqual(updated.status_code, status.HTTP_200_OK)
		self.assertEqual(updated.data['status'], ListingInquiry.Status.CONTACTED)
		viewing_id = updated.data['viewing_request']['id']
		confirmed = self.client.patch(reverse('marketplace:agent-viewing-status-update', kwargs={'pk': viewing_id}), {
			'status': ViewingRequest.Status.CONFIRMED,
		}, format='json')
		self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
		self.assertEqual(confirmed.data['status'], ViewingRequest.Status.CONFIRMED)

	def test_suspended_agent_cannot_access_workspace_or_make_listing_changes(self):
		self._grant()
		created = self._create_agent_draft()
		listing = Listing.objects.get(pk=created.data['id'])
		self.agent.account_status = AgentProfile.AccountStatus.SUSPENDED
		self.agent.save(update_fields=('account_status',))
		self.client.force_authenticate(self.agent_user)
		self.assertEqual(self.client.get(reverse('marketplace:agent-profile')).status_code, status.HTTP_403_FORBIDDEN)
		self.assertEqual(self.client.get(reverse('marketplace:agent-listing-list')).status_code, status.HTTP_403_FORBIDDEN)
		self.assertEqual(self.client.post(reverse('marketplace:agent-listing-publish', kwargs={'pk': listing.pk})).status_code, status.HTTP_403_FORBIDDEN)
