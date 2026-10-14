from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.marketplace.models import Listing
from apps.organizations.models import Organization
from apps.properties.models import Building, Property, Unit


class PublicMarketplaceDiscoveryTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="public-marketplace-owner",
            password="SafePass123!",
        )
        self.organization = Organization.objects.create(name="Nairobi Homes")
        self.property = Property.objects.create(
            organization=self.organization,
            name="Kilimani Garden Court",
            city="Nairobi",
        )
        self.building = Building.objects.create(property=self.property, name="Block A")
        self.url = reverse("marketplace:public-listing-list")

    def create_listing(self, index=0, **overrides):
        unit = Unit.objects.create(
            building=self.building,
            name=f"A-{index + 1:02d}",
            bedrooms=1,
        )
        values = {
            "unit": unit,
            "created_by": self.user,
            "title": f"Kilimani home {index + 1}",
            "description": "Quiet courtyard apartment with parking.",
            "monthly_rent_minor": 4_500_000,
            "bedrooms": 1,
            "bathrooms": 1,
            "amenities": ["Parking", "Water"],
            "area": "Kilimani",
            "city": "Nairobi",
            "status": Listing.Status.PUBLISHED,
            "published_at": timezone.now(),
        }
        values.update(overrides)
        return Listing.objects.create(**values)

    def results(self, response):
        return response.data["results"]

    def test_keyword_filters_and_price_range_validation(self):
        matched = self.create_listing(title="Orchid home")
        self.create_listing(index=1, title="South B apartment", area="South B")

        response = self.client.get(self.url, {"q": "orchid", "amenity": ["Parking", "Water"]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in self.results(response)], [str(matched.pk)])

        invalid_range = self.client.get(self.url, {"min_rent": 500_000, "max_rent": 400_000})
        self.assertEqual(invalid_range.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_keyword = self.client.get(self.url, {"q": "x" * 101})
        self.assertEqual(invalid_keyword.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_location = self.client.get(self.url, {"location": "x" * 101})
        self.assertEqual(invalid_location.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_rent = self.client.get(self.url, {"min_rent": 9_223_372_036_854_775_808})
        self.assertEqual(invalid_rent.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_bedrooms = self.client.get(self.url, {"bedrooms": 31})
        self.assertEqual(invalid_bedrooms.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_amenity = self.client.get(self.url, {"amenity": "x" * 41})
        self.assertEqual(invalid_amenity.status_code, status.HTTP_400_BAD_REQUEST)

    def test_public_results_are_paginated_with_a_bounded_page_size(self):
        for index in range(55):
            self.create_listing(index=index)

        first = self.client.get(self.url, {"page": 1, "page_size": 2})
        second = self.client.get(self.url, {"page": 2, "page_size": 2})
        oversized = self.client.get(self.url, {"page": 1, "page_size": 1000})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["count"], 55)
        self.assertEqual(len(first.data["results"]), 2)
        self.assertIsNotNone(first.data["next"])
        self.assertIsNone(first.data["previous"])
        self.assertEqual(len(second.data["results"]), 2)
        self.assertIsNotNone(second.data["previous"])
        self.assertEqual(len(oversized.data["results"]), 48)

    def test_inactive_organization_and_property_are_hidden_from_list_and_detail(self):
        organization_listing = self.create_listing()
        property_listing = self.create_listing(index=1, title="Other home")

        self.organization.is_active = False
        self.organization.save(update_fields=("is_active",))
        response = self.client.get(self.url)
        detail = self.client.get(
            reverse("marketplace:public-listing-detail", kwargs={"pk": organization_listing.pk})
        )
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

        self.organization.is_active = True
        self.organization.save(update_fields=("is_active",))
        self.property.is_active = False
        self.property.save(update_fields=("is_active",))
        response = self.client.get(self.url)
        detail = self.client.get(
            reverse("marketplace:public-listing-detail", kwargs={"pk": property_listing.pk})
        )
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)
