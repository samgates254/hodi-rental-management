from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.organizations.models import Organization, OrganizationMembership


class OrganizationMembershipTests(TestCase):
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
