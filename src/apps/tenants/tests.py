from django.test import TestCase

from apps.organizations.models import Organization
from apps.tenants.models import Tenant


class TenantTests(TestCase):
    def test_full_name_is_derived_from_name_parts(self):
        organization = Organization.objects.create(
            name='Rongai Homes',
            slug='rongai-homes',
        )
        tenant = Tenant.objects.create(
            organization=organization,
            first_name='Amina',
            last_name='Otieno',
            phone_number='+254700000000',
        )

        self.assertEqual(tenant.full_name, 'Amina Otieno')
