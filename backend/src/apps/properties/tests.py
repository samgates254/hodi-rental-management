from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.organizations.models import Organization
from apps.properties.models import Building, Property, Unit


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
