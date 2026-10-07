from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.leases.models import Lease, LeaseAmendment
from apps.notifications.models import Notification
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant


class LeaseLifecycleTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username='owner', password='password')
        self.tenant_user = user_model.objects.create_user(username='tenant', password='password')
        self.organization = Organization.objects.create(name='Rongai Homes')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
        )
        self.tenant = Tenant.objects.create(
            organization=self.organization,
            user=self.tenant_user,
            first_name='Amina',
            last_name='Otieno',
            phone_number='+254700000010',
        )
        property_record = Property.objects.create(organization=self.organization, name='Acacia')
        building = Building.objects.create(property=property_record, name='Block A')
        self.unit = Unit.objects.create(building=building, name='A-1')
        self.lease = Lease.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            reference='L-1',
            start_date=date(2026, 1, 1),
            monthly_rent_minor=100000,
        )
        self.client.force_authenticate(self.owner)

    def test_activate_occupies_unit_and_writes_audit_and_notification(self):
        response = self.client.post(f'/api/v1/leases/{self.lease.pk}/activate/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.ACTIVE)
        self.assertEqual(self.unit.status, Unit.Status.OCCUPIED)
        self.assertTrue(AuditLog.objects.filter(action='lease.activate', object_id=str(self.lease.pk)).exists())
        self.assertTrue(Notification.objects.filter(user=self.tenant_user, type='LEASE_ACTIVATED').exists())

    def test_terminate_frees_unit_and_records_amendment(self):
        self.client.post(f'/api/v1/leases/{self.lease.pk}/activate/')
        response = self.client.post(
            f'/api/v1/leases/{self.lease.pk}/terminate/',
            {'end_date': '2026-06-01', 'reason': 'Moved out'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.TERMINATED)
        self.assertEqual(self.lease.end_date, date(2026, 6, 1))
        self.assertEqual(self.unit.status, Unit.Status.AVAILABLE)
        amendment = LeaseAmendment.objects.get(lease=self.lease)
        self.assertEqual(amendment.amendment_type, LeaseAmendment.AmendmentType.TERMINATION)
        self.assertTrue(Notification.objects.filter(user=self.tenant_user, type='LEASE_TERMINATED').exists())

    def test_expire_requires_a_past_end_date(self):
        self.lease.status = Lease.Status.ACTIVE
        self.lease.end_date = timezone.localdate() - timedelta(days=1)
        self.lease.save(update_fields=('status', 'end_date', 'updated_at'))
        self.unit.status = Unit.Status.OCCUPIED
        self.unit.save(update_fields=('status', 'updated_at'))
        response = self.client.post(f'/api/v1/leases/{self.lease.pk}/expire/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, Unit.Status.AVAILABLE)
