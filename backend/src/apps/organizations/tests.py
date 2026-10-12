from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse

from apps.organizations.models import Organization, OrganizationMembership
from apps.audit.models import AuditLog


class OrganizationMembershipTests(TestCase):
    def test_slug_is_generated_from_name(self):
        organization = Organization.objects.create(name='Rongai Homes')

        self.assertEqual(organization.slug, 'rongai-homes')

    def test_duplicate_generated_slugs_receive_a_suffix(self):
        first = Organization.objects.create(name='Rongai Homes')
        second = Organization.objects.create(name='Rongai Homes')

        self.assertEqual(first.slug, 'rongai-homes')
        self.assertEqual(second.slug, 'rongai-homes-2')


class AccountantInvitationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username='invite-owner', email='owner@example.test', password='safe-password')
        self.accountant = User.objects.create_user(username='invite-accountant', email='accountant@example.test', password='safe-password')
        self.stranger = User.objects.create_user(username='invite-stranger', email='stranger@example.test', password='safe-password')
        self.organization = Organization.objects.create(name='Invitation Client')
        OrganizationMembership.objects.create(organization=self.organization, user=self.owner, role=OrganizationMembership.Role.OWNER)

    def test_invitation_is_bound_accepted_idempotently_and_revocation_removes_access(self):
        self.client.force_authenticate(self.owner)
        created = self.client.post(reverse('organizations:accountant-invitations'),
            {'organization': self.organization.pk, 'email': self.accountant.email}, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        invite_id = created.data['id']
        self.client.force_authenticate(self.stranger)
        denied = self.client.post(reverse('organizations:accountant-invitation-action', kwargs={'invitation_id': invite_id, 'action': 'accept'}))
        self.assertEqual(denied.status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.accountant)
        accepted = self.client.post(reverse('organizations:accountant-invitation-action', kwargs={'invitation_id': invite_id, 'action': 'accept'}))
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        again = self.client.post(reverse('organizations:accountant-invitation-action', kwargs={'invitation_id': invite_id, 'action': 'accept'}))
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertTrue(OrganizationMembership.objects.get(organization=self.organization,user=self.accountant).is_active)
        self.client.force_authenticate(self.owner)
        revoked = self.client.post(reverse('organizations:accountant-invitation-action', kwargs={'invitation_id': invite_id, 'action': 'revoke'}))
        self.assertEqual(revoked.status_code, status.HTTP_200_OK)
        self.assertFalse(OrganizationMembership.objects.get(organization=self.organization,user=self.accountant).is_active)
        self.assertEqual(AuditLog.objects.filter(object_type='AccountantInvitation', object_id=str(invite_id)).count(), 3)

    def test_only_owner_can_invite_and_existing_direct_accountant_creation_is_refused(self):
        self.client.force_authenticate(self.stranger)
        denied = self.client.post(reverse('organizations:accountant-invitations'),
            {'organization': self.organization.pk, 'email': self.accountant.email}, format='json')
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

    def test_membership_connects_user_to_organization_and_role(self):
        user = get_user_model().objects.create_user(
            username='manager',
            password='password',
        )
        organization = Organization.objects.create(
            name='Rongai Homes',
            slug='rongai-homes',
        )

        membership = OrganizationMembership.objects.create(
            organization=organization,
            user=user,
            role=OrganizationMembership.Role.PROPERTY_MANAGER,
        )

        self.assertEqual(membership.user, user)
        self.assertEqual(membership.organization, organization)
        self.assertEqual(membership.role, OrganizationMembership.Role.PROPERTY_MANAGER)

    def test_membership_is_unique_per_user_and_organization(self):
        user = get_user_model().objects.create_user(
            username='manager',
            password='password',
        )
        organization = Organization.objects.create(
            name='Rongai Homes',
            slug='rongai-homes',
        )
        OrganizationMembership.objects.create(
            organization=organization,
            user=user,
            role=OrganizationMembership.Role.PROPERTY_MANAGER,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationMembership.objects.create(
                    organization=organization,
                    user=user,
                    role=OrganizationMembership.Role.ACCOUNTANT,
                )
