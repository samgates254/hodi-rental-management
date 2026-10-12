from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.maintenance.models import TechnicianProfile
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

    def test_owner_cannot_grant_accountant_via_generic_membership_api(self):
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

        self.assertEqual(update_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_owner_membership_api_provisions_technician_profile(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            reverse('organizations:membership-list'),
            {
                'organization': self.organization.pk,
                'user': self.candidate.pk,
                'role': OrganizationMembership.Role.TECHNICIAN,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        membership = OrganizationMembership.objects.get(user=self.candidate)
        self.assertEqual(membership.organization, self.organization)
        self.assertEqual(membership.role, OrganizationMembership.Role.TECHNICIAN)
        profile = TechnicianProfile.objects.get(user=self.candidate)
        self.assertTrue(profile.verified)
        self.assertTrue(profile.available)

    def test_owner_can_create_manager_caretaker_and_technician_accounts(self):
        self.client.force_authenticate(self.owner)
        password = 'Manager-strong-password-243!'
        created = []
        for role, username in (
            (OrganizationMembership.Role.PROPERTY_MANAGER, 'new-manager'),
            (OrganizationMembership.Role.CARETAKER, 'new-caretaker'),
            (OrganizationMembership.Role.TECHNICIAN, 'new-technician'),
        ):
            response = self.client.post(
                reverse('organizations:staff'),
                {
                    'organization': self.organization.pk,
                    'username': username,
                    'email': f'{username}@example.com',
                    'first_name': 'Casey',
                    'last_name': 'Staff',
                    'phone_number': '+254712345678',
                    'role': role,
                    'password': password,
                    'password_confirm': password,
                },
                format='json',
            )

            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(response.data['role'], role)
            self.assertEqual(response.data['username'], username)
            created.append((username, role))

        for username, role in created:
            user = get_user_model().objects.get(username=username)
            self.assertTrue(user.check_password(password))
            self.assertEqual(user.account_profile.account_type, 'UNSPECIFIED')
            membership = user.organization_memberships.get()
            self.assertEqual(membership.role, role)
            self.assertEqual(membership.organization, self.organization)

            if role == OrganizationMembership.Role.TECHNICIAN:
                technician_profile = TechnicianProfile.objects.get(user=user)
                self.assertTrue(technician_profile.verified)
                self.assertTrue(technician_profile.available)

            login_response = self.client.post(
                '/api/v1/accounts/login/',
                {'username': username, 'password': password},
                format='json',
            )
            self.assertEqual(login_response.status_code, status.HTTP_200_OK)
            self.assertEqual(login_response.data['memberships'][0]['role'], role)

            if role == OrganizationMembership.Role.TECHNICIAN:
                self.client.force_authenticate(user)
                maintenance_response = self.client.get('/api/v1/maintenance/requests/')
                property_response = self.client.get('/api/v1/properties/')
                self.assertEqual(maintenance_response.status_code, status.HTTP_200_OK)
                self.assertEqual(property_response.status_code, status.HTTP_403_FORBIDDEN)
                self.client.force_authenticate(self.owner)

    def test_owner_cannot_grant_accountant_access_without_invitation_acceptance(self):
        self.client.force_authenticate(self.owner)
        password = 'Accountant-strong-password-243!'
        response = self.client.post(
            reverse('organizations:staff'),
            {
                'organization': self.organization.pk,
                'username': 'new-accountant',
                'email': 'new-accountant@example.com',
                'first_name': 'Amina',
                'last_name': 'Books',
                'phone_number': '+254712000111',
                'role': OrganizationMembership.Role.ACCOUNTANT,
                'password': password,
                'password_confirm': password,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(get_user_model().objects.filter(username='new-accountant').exists())

    def test_staff_endpoint_rejects_privileged_or_unsupported_roles(self):
        self.client.force_authenticate(self.owner)
        password = 'Strong-password-243!'
        for role, username in (
            (OrganizationMembership.Role.OWNER, 'forged-owner'),
            (OrganizationMembership.Role.SUPPORT, 'forged-support'),
        ):
            with self.subTest(role=role):
                response = self.client.post(
                    reverse('organizations:staff'),
                    {
                        'organization': self.organization.pk,
                        'username': username,
                        'email': f'{username}@example.com',
                        'first_name': 'Forged',
                        'last_name': 'Role',
                        'role': role,
                        'password': password,
                        'password_confirm': password,
                    },
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertFalse(get_user_model().objects.filter(username=username).exists())

    def test_staff_listing_includes_existing_accountants_and_new_technicians(self):
        existing_accountant = get_user_model().objects.create_user(
            username='existing-accountant',
            password='password',
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=existing_accountant,
            role=OrganizationMembership.Role.ACCOUNTANT,
        )
        technician = get_user_model().objects.create_user(
            username='existing-technician',
            password='password',
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=technician,
            role=OrganizationMembership.Role.TECHNICIAN,
        )

        self.client.force_authenticate(self.owner)
        response = self.client.get(
            reverse('organizations:staff'),
            {'organization': self.organization.pk},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        listed_roles = {row['username']: row['role'] for row in response.data}
        self.assertEqual(listed_roles['existing-accountant'], OrganizationMembership.Role.ACCOUNTANT)
        self.assertEqual(listed_roles['existing-technician'], OrganizationMembership.Role.TECHNICIAN)

    def test_non_owner_cannot_create_staff_accounts(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(
            reverse('organizations:staff'),
            {
                'organization': self.organization.pk,
                'username': 'unauthorized-staff',
                'email': 'unauthorized-staff@example.com',
                'first_name': 'Unauth',
                'last_name': 'Staff',
                'role': OrganizationMembership.Role.CARETAKER,
                'password': 'Manager-strong-password-243!',
                'password_confirm': 'Manager-strong-password-243!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            get_user_model().objects.filter(username='unauthorized-staff').exists(),
        )

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
