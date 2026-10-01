from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Property


class PropertyRoleAuthorizationTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='portfolio-user',
            password='password',
        )
        self.organization = Organization.objects.create(name='Rongai Homes')
        self.other_organization = Organization.objects.create(name='Other Homes')
        self.property = Property.objects.create(
            organization=self.organization,
            name='Acacia Court',
        )
        self.property_url = reverse(
            'properties:property-detail',
            args=(self.property.pk,),
        )

    def add_membership(self, organization, role):
        return OrganizationMembership.objects.create(
            organization=organization,
            user=self.user,
            role=role,
        )

    def test_accountant_can_read_but_not_write_properties(self):
        self.add_membership(
            self.organization,
            OrganizationMembership.Role.ACCOUNTANT,
        )
        self.client.force_authenticate(self.user)

        read_response = self.client.get(self.property_url)
        update_response = self.client.patch(
            self.property_url,
            {'name': 'Changed Court'},
            format='json',
        )
        create_response = self.client.post(
            reverse('properties:property-list'),
            {'organization': self.organization.pk, 'name': 'New Court'},
            format='json',
        )

        self.assertEqual(read_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_role_in_another_organization_does_not_grant_write_access(self):
        self.add_membership(
            self.organization,
            OrganizationMembership.Role.ACCOUNTANT,
        )
        self.add_membership(
            self.other_organization,
            OrganizationMembership.Role.PROPERTY_MANAGER,
        )
        self.client.force_authenticate(self.user)

        response = self.client.patch(
            self.property_url,
            {'name': 'Changed Court'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_property_cannot_be_reassigned_without_destination_write_access(self):
        self.add_membership(
            self.organization,
            OrganizationMembership.Role.PROPERTY_MANAGER,
        )
        self.add_membership(
            self.other_organization,
            OrganizationMembership.Role.ACCOUNTANT,
        )
        self.client.force_authenticate(self.user)

        response = self.client.patch(
            self.property_url,
            {'organization': self.other_organization.pk},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.property.refresh_from_db()
        self.assertEqual(self.property.organization, self.organization)