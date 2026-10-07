from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.organizations.models import Organization, OrganizationMembership


class AuditApiTests(APITestCase):
    def test_append_only_and_role_scoped_list(self):
        user_model = get_user_model()
        owner = user_model.objects.create_user(username='owner', password='password')
        technician = user_model.objects.create_user(username='tech', password='password')
        organization = Organization.objects.create(name='Rongai Homes')
        other = Organization.objects.create(name='Other Homes')
        OrganizationMembership.objects.create(
            organization=organization, user=owner, role=OrganizationMembership.Role.OWNER,
        )
        OrganizationMembership.objects.create(
            organization=organization, user=technician, role=OrganizationMembership.Role.TECHNICIAN,
        )
        row = AuditLog.objects.create(
            actor=owner,
            organization=organization,
            action='invoice.post',
            object_type='Invoice',
            object_id='9',
            metadata={'total_cents': 100},
        )
        AuditLog.objects.create(
            actor=owner,
            organization=other,
            action='invoice.post',
            object_type='Invoice',
            object_id='8',
        )
        with self.assertRaises(ValidationError):
            row.action = 'changed'
            row.save()
        with self.assertRaises(ValidationError):
            row.delete()

        self.client.force_authenticate(technician)
        denied = self.client.get('/api/v1/audit/logs/')
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(owner)
        listing = self.client.get('/api/v1/audit/logs/', {'object_type': 'Invoice', 'object_id': '9'})
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.data), 1)
        self.assertEqual(listing.data[0]['action'], 'invoice.post')
        self.assertEqual(self.client.post('/api/v1/audit/logs/', {}, format='json').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
