from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
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

    def test_create_cannot_activate_lease_outside_lifecycle_action(self):
        response = self.client.post(
            reverse('leases:lease-list'),
            {
                'tenant': self.tenant.pk,
                'unit': self.unit.pk,
                'reference': 'L-2',
                'start_date': '2026-02-01',
                'monthly_rent_minor': 100000,
                'status': Lease.Status.ACTIVE,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', response.data)
        self.assertFalse(Lease.objects.filter(reference='L-2').exists())
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, Unit.Status.AVAILABLE)
        self.assertFalse(AuditLog.objects.filter(action='lease.activate').exists())

    def test_patch_cannot_activate_terminate_or_expire_lease(self):
        detail_url = reverse('leases:lease-detail', args=(self.lease.pk,))
        activation = self.client.patch(
            detail_url, {'status': Lease.Status.ACTIVE}, format='json',
        )
        self.assertEqual(activation.status_code, status.HTTP_400_BAD_REQUEST)
        self.lease.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.DRAFT)

        activated = self.client.post(f'/api/v1/leases/{self.lease.pk}/activate/')
        self.assertEqual(activated.status_code, status.HTTP_200_OK)
        for requested_status in (Lease.Status.TERMINATED, Lease.Status.EXPIRED):
            with self.subTest(requested_status=requested_status):
                response = self.client.patch(
                    detail_url, {'status': requested_status}, format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.lease.refresh_from_db()
                self.assertEqual(self.lease.status, Lease.Status.ACTIVE)

    def test_create_explicit_draft_and_lifecycle_activation_work(self):
        second_unit = Unit.objects.create(building=self.unit.building, name='A-2')
        response = self.client.post(
            reverse('leases:lease-list'),
            {
                'tenant': self.tenant.pk,
                'unit': second_unit.pk,
                'reference': 'L-2',
                'start_date': '2026-02-01',
                'monthly_rent_minor': 100000,
                'status': Lease.Status.DRAFT,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        lease_id = response.data['id']
        activated = self.client.post(f'/api/v1/leases/{lease_id}/activate/')
        self.assertEqual(activated.status_code, status.HTTP_200_OK)
        self.assertEqual(activated.data['status'], Lease.Status.ACTIVE)
