from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.subscriptions.models import OrganizationSubscription, SubscriptionPlan


class PropertyHierarchyTests(TestCase):
    def test_unit_exposes_its_organization_boundary(self):
        organization = Organization.objects.create(
            name='Rongai Homes',
            slug='rongai-homes',
        )
        property_record = Property.objects.create(
            organization=organization,
            name='Acacia Court',
        )
        building = Building.objects.create(
            property=property_record,
            name='Block A',
        )
        unit = Unit.objects.create(
            building=building,
            name='A-01',
        )

        concrete_field_names = {field.name for field in Unit._meta.concrete_fields}
        self.assertNotIn('organization', concrete_field_names)
        self.assertEqual(unit.organization_id, organization.id)
        self.assertEqual(unit.status, Unit.Status.AVAILABLE)

    def test_property_name_is_unique_within_an_organization(self):
        organization = Organization.objects.create(
            name='Rongai Homes',
            slug='rongai-homes',
        )
        Property.objects.create(
            organization=organization,
            name='Acacia Court',
        )

        duplicate = Property(
            organization=organization,
            name='Acacia Court',
        )

        with self.assertRaises(ValidationError):
            duplicate.validate_constraints()


class UnitSubscriptionCapacityApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username='unit-capacity-owner',
            password='test-password',
        )
        self.organization = Organization.objects.create(name='Unit Capacity Homes')
        self.other_organization = Organization.objects.create(name='Other Capacity Homes')
        for organization in (self.organization, self.other_organization):
            OrganizationMembership.objects.create(
                organization=organization,
                user=self.owner,
                role=OrganizationMembership.Role.OWNER,
            )
        self.property = Property.objects.create(
            organization=self.organization,
            name='Capacity Property',
        )
        self.building = Building.objects.create(property=self.property, name='Block A')
        self.other_property = Property.objects.create(
            organization=self.other_organization,
            name='Other Capacity Property',
        )
        self.other_building = Building.objects.create(property=self.other_property, name='Block B')
        self.subscription = OrganizationSubscription.objects.get(organization=self.organization)
        self.client.force_authenticate(self.owner)

    def create_units(self, building, count, prefix='Unit'):
        return [
            Unit.objects.create(building=building, name=f'{prefix} {index + 1}')
            for index in range(count)
        ]

    def update_url(self, unit):
        return reverse('properties:unit-detail', args=(unit.pk,))

    def test_update_within_organization_is_allowed_at_unit_limit(self):
        units = self.create_units(self.building, 5)

        response = self.client.patch(
            self.update_url(units[0]),
            {'name': 'Renamed Unit'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        units[0].refresh_from_db()
        self.assertEqual(units[0].name, 'Renamed Unit')

    def test_unit_can_move_between_organizations_with_different_limits(self):
        starter = SubscriptionPlan.objects.get(code='starter', is_active=True)
        self.subscription.plan = starter
        self.subscription.status = OrganizationSubscription.Status.ACTIVE
        self.subscription.save(update_fields=('plan', 'status', 'updated_at'))
        self.create_units(self.other_building, 4, prefix='Destination')
        unit = self.create_units(self.building, 1)[0]

        response = self.client.patch(
            self.update_url(unit),
            {'building': self.other_building.pk},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        unit.refresh_from_db()
        self.assertEqual(unit.building_id, self.other_building.pk)
        self.assertEqual(
            Unit.objects.filter(building__property__organization=self.other_organization)
            .exclude(status=Unit.Status.INACTIVE).count(),
            5,
        )
        self.assertEqual(
            Unit.objects.filter(building__property__organization=self.organization)
            .exclude(status=Unit.Status.INACTIVE).count(),
            0,
        )

    def test_moving_unit_into_full_lower_limit_organization_is_blocked(self):
        starter = SubscriptionPlan.objects.get(code='starter', is_active=True)
        self.subscription.plan = starter
        self.subscription.status = OrganizationSubscription.Status.ACTIVE
        self.subscription.save(update_fields=('plan', 'status', 'updated_at'))
        self.create_units(self.other_building, 5, prefix='Destination')
        unit = self.create_units(self.building, 1)[0]

        response = self.client.patch(
            self.update_url(unit),
            {'building': self.other_building.pk},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'UNIT_LIMIT_REACHED')
        unit.refresh_from_db()
        self.assertEqual(unit.building_id, self.building.pk)

    def test_marking_unit_inactive_frees_capacity(self):
        units = self.create_units(self.building, 5)

        response = self.client.patch(
            self.update_url(units[0]),
            {'status': Unit.Status.INACTIVE},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        units[0].refresh_from_db()
        self.assertEqual(units[0].status, Unit.Status.INACTIVE)
        created = self.client.post(
            reverse('properties:unit-list'),
            {'building': self.building.pk, 'name': 'Replacement Unit'},
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

    def test_organization_cannot_create_unit_beyond_its_limit(self):
        self.create_units(self.building, 5)

        response = self.client.post(
            reverse('properties:unit-list'),
            {'building': self.building.pk, 'name': 'Over-limit Unit'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'UNIT_LIMIT_REACHED')
        self.assertEqual(
            Unit.objects.filter(building__property__organization=self.organization).count(),
            5,
        )
