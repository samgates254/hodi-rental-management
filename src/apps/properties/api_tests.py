from rest_framework import status
from rest_framework.test import APITestCase

from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Property
from django.contrib.auth import get_user_model


class PropertyApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='manager',
            password='password',
        )
        self.other_user = get_user_model().objects.create_user(
            username='other-manager',
            password='password',
        )
        self.organization = Organization.objects.create(
            name='Rongai Homes',
            slug='rongai-homes',
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.PROPERTY_MANAGER,
        )
        self.other_organization = Organization.objects.create(
            name='Other Homes',
            slug='other-homes',
        )
        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.other_user,
            role=OrganizationMembership.Role.PROPERTY_MANAGER,
        )

    def test_authenticated_user_can_create_property_in_own_organization(self):
        self.client.force_authenticate(self.user)

        response = self.client.post('/api/v1/properties/', {
            'organization': self.organization.id,
            'name': 'Acacia Court',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Property.objects.filter(name='Acacia Court').exists())

    def test_user_cannot_list_another_organization_property(self):
        Property.objects.create(
            organization=self.other_organization,
            name='Hidden Court',
        )
        self.client.force_authenticate(self.user)

        response = self.client.get('/api/v1/properties/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), [])
