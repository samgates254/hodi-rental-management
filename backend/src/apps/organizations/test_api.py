from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.organizations.models import Organization, OrganizationMembership


class OrganizationMembershipAuthorizationTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username='owner',
            password='password',
        )
        self.member = user_model.objects.create_user(
            username='member',
            password='password',
        )
        self.candidate = user_model.objects.create_user(
            username='candidate',
            password='password',
        )
        Organization.objects.create(name='Unrelated Homes')
        self.organization = Organization.objects.create(name='Rongai Homes')
        self.owner_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
        )
        self.member_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member,
            role=OrganizationMembership.Role.PROPERTY_MANAGER,
        )

    def test_regular_member_cannot_create_promote_or_remove_memberships(self):
        self.client.force_authenticate(self.member)

        create_response = self.client.post(
            reverse('organizations:membership-list'),
            {
                'organization': self.organization.pk,
                'user': self.candidate.pk,
                'role': OrganizationMembership.Role.OWNER,
            },
            format='json',
        )
        update_response = self.client.patch(
            reverse('organizations:membership-detail', args=(self.member_membership.pk,)),
            {'role': OrganizationMembership.Role.OWNER},
            format='json',
        )
        delete_response = self.client.delete(
            reverse('organizations:membership-detail', args=(self.owner_membership.pk,)),
        )

        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(update_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            OrganizationMembership.objects.filter(user=self.candidate).exists(),
        )
        self.member_membership.refresh_from_db()
        self.assertEqual(
            self.member_membership.role,
            OrganizationMembership.Role.PROPERTY_MANAGER,
        )

    def test_regular_member_cannot_update_organization(self):
        self.client.force_authenticate(self.member)

        response = self.client.patch(
            reverse('organizations:organization-detail', args=(self.organization.pk,)),
            {'name': 'Changed Name'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_regular_member_cannot_delete_organization(self):
        self.client.force_authenticate(self.member)

        response = self.client.delete(
            reverse('organizations:organization-detail', args=(self.organization.pk,)),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_manage_non_owner_memberships(self):
        self.client.force_authenticate(self.owner)
        membership_url = reverse(
            'organizations:membership-detail',
            args=(self.member_membership.pk,),
        )

        update_response = self.client.patch(
            membership_url,
            {'role': OrganizationMembership.Role.ACCOUNTANT},
            format='json',
        )
        create_response = self.client.post(
            reverse('organizations:membership-list'),
            {
                'organization': self.organization.pk,
                'user': self.candidate.pk,
                'role': OrganizationMembership.Role.CARETAKER,
            },
            format='json',
        )
        delete_response = self.client.delete(membership_url)

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_membership_cannot_be_moved_to_another_organization(self):
        self.client.force_authenticate(self.owner)
        other_organization = Organization.objects.create(name='Other Homes')

        response = self.client.patch(
            reverse(
                'organizations:membership-detail',
                args=(self.member_membership.pk,),
            ),
            {'organization': other_organization.pk},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.organization, self.organization)

    def test_owner_cannot_remove_or_demote_the_last_active_owner(self):
        self.client.force_authenticate(self.owner)
        owner_url = reverse(
            'organizations:membership-detail',
            args=(self.owner_membership.pk,),
        )

        demote_response = self.client.patch(
            owner_url,
            {'role': OrganizationMembership.Role.SUPPORT},
            format='json',
        )
        deactivate_response = self.client.patch(
            owner_url,
            {'is_active': False},
            format='json',
        )
        delete_response = self.client.delete(owner_url)

        self.assertEqual(demote_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(deactivate_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(delete_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.owner_membership.refresh_from_db()
        self.assertTrue(self.owner_membership.is_active)
        self.assertEqual(self.owner_membership.role, OrganizationMembership.Role.OWNER)