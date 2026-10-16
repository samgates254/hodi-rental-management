from datetime import date, timedelta
from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.leases.models import Lease, LeaseAmendment
from apps.notifications.models import Notification
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant
from common.rental_dates import rental_business_date


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
        with patch('application.services.leases.rental_business_date', return_value=date(2026, 10, 15)):
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

    @skipUnless(connection.vendor == 'postgresql', 'PostgreSQL row-lock semantics required.')
    def test_termination_does_not_lock_nullable_tenant_user_join(self):
        self.tenant.user = None
        self.tenant.save(update_fields=('user', 'updated_at'))
        self.lease.status = Lease.Status.ACTIVE
        self.lease.save(update_fields=('status', 'updated_at'))
        self.unit.status = Unit.Status.OCCUPIED
        self.unit.save(update_fields=('status', 'updated_at'))

        with patch('application.services.leases.rental_business_date', return_value=date(2026, 10, 15)):
            response = self.client.post(
                f'/api/v1/leases/{self.lease.pk}/terminate/',
                {'end_date': '2026-06-01', 'reason': 'Tenant moved out'},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.TERMINATED)
        self.assertEqual(self.unit.status, Unit.Status.AVAILABLE)

    def test_termination_cannot_release_a_unit_before_its_inclusive_end_date(self):
        self.client.post(f'/api/v1/leases/{self.lease.pk}/activate/')
        with patch('application.services.leases.rental_business_date', return_value=date(2026, 10, 15)):
            response = self.client.post(
                f'/api/v1/leases/{self.lease.pk}/terminate/',
                {'end_date': '2026-10-16', 'reason': 'Future move-out'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.ACTIVE)
        self.assertEqual(self.unit.status, Unit.Status.OCCUPIED)

    def test_expire_requires_a_past_end_date(self):
        self.lease.status = Lease.Status.ACTIVE
        self.lease.end_date = date(2026, 10, 14)
        self.lease.save(update_fields=('status', 'end_date', 'updated_at'))
        self.unit.status = Unit.Status.OCCUPIED
        self.unit.save(update_fields=('status', 'updated_at'))
        with patch('application.services.leases.rental_business_date', return_value=date(2026, 10, 14)):
            still_inclusive = self.client.post(f'/api/v1/leases/{self.lease.pk}/expire/')
        self.assertEqual(still_inclusive.status_code, status.HTTP_400_BAD_REQUEST)
        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.ACTIVE)
        self.assertEqual(self.unit.status, Unit.Status.OCCUPIED)
        with patch('application.services.leases.rental_business_date', return_value=date(2026, 10, 15)):
            response = self.client.post(f'/api/v1/leases/{self.lease.pk}/expire/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.EXPIRED)
        self.assertEqual(self.unit.status, Unit.Status.AVAILABLE)
        with patch('application.services.leases.rental_business_date', return_value=date(2026, 10, 15)):
            repeated = self.client.post(f'/api/v1/leases/{self.lease.pk}/expire/')
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)

    def test_termination_on_inclusive_final_day_schedules_end_without_revoking_access(self):
        self.client.post(f'/api/v1/leases/{self.lease.pk}/activate/')
        final_day = date(2026, 10, 15)
        terminate_url = f'/api/v1/leases/{self.lease.pk}/terminate/'
        with patch('application.services.leases.rental_business_date', return_value=final_day):
            response = self.client.post(
                terminate_url,
                {'end_date': final_day.isoformat(), 'reason': 'Move out at end of day'},
                format='json',
            )
            repeated = self.client.post(
                terminate_url,
                {'end_date': final_day.isoformat(), 'reason': 'Move out at end of day'},
                format='json',
            )
            premature_expiry = self.client.post(f'/api/v1/leases/{self.lease.pk}/expire/')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK, repeated.data)
        self.assertEqual(premature_expiry.status_code, status.HTTP_400_BAD_REQUEST)
        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.ACTIVE)
        self.assertEqual(self.lease.end_date, final_day)
        self.assertEqual(self.unit.status, Unit.Status.OCCUPIED)
        self.assertEqual(LeaseAmendment.objects.filter(lease=self.lease).count(), 1)
        self.assertTrue(Notification.objects.filter(user=self.tenant_user, type='LEASE_END_SCHEDULED').exists())
        self.assertFalse(Notification.objects.filter(user=self.tenant_user, type='LEASE_TERMINATED').exists())

        self.client.force_authenticate(self.tenant_user)
        final_day_instant = datetime(2026, 10, 14, 22, 30, tzinfo=datetime_timezone.utc)
        with patch('django.utils.timezone.now', return_value=final_day_instant):
            maintenance_request = self.client.post('/api/v1/maintenance/issues/', {
                'unit': self.unit.pk,
                'title': 'Final-day maintenance request',
                'category': 'PLUMBING',
                'priority': 'NORMAL',
                'description': 'A repair issue on the last lease day.',
            }, format='json')
        self.assertEqual(maintenance_request.status_code, status.HTTP_201_CREATED, maintenance_request.data)
        self.client.force_authenticate(self.owner)

        with patch('application.services.leases.rental_business_date', return_value=final_day + timedelta(days=1)):
            finalized = self.client.post(f'/api/v1/leases/{self.lease.pk}/expire/')
            repeated_finalization = self.client.post(f'/api/v1/leases/{self.lease.pk}/expire/')
        self.assertEqual(finalized.status_code, status.HTTP_200_OK, finalized.data)
        self.assertEqual(repeated_finalization.status_code, status.HTTP_200_OK, repeated_finalization.data)
        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.TERMINATED)
        self.assertEqual(self.unit.status, Unit.Status.AVAILABLE)
        self.assertEqual(LeaseAmendment.objects.filter(lease=self.lease).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.tenant_user, type='LEASE_TERMINATED').count(), 1)

    def test_idempotent_expiry_does_not_release_terminated_tenancy_on_its_final_day(self):
        self.lease.status = Lease.Status.TERMINATED
        self.lease.end_date = date(2026, 10, 15)
        self.lease.save(update_fields=('status', 'end_date', 'updated_at'))
        self.unit.status = Unit.Status.OCCUPIED
        self.unit.save(update_fields=('status', 'updated_at'))

        with patch('application.services.leases.rental_business_date', return_value=date(2026, 10, 15)):
            response = self.client.post(f'/api/v1/leases/{self.lease.pk}/expire/')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, Unit.Status.OCCUPIED)

    def test_authorized_early_termination_keeps_effective_date_and_releases_unit(self):
        self.client.post(f'/api/v1/leases/{self.lease.pk}/activate/')
        with patch('application.services.leases.rental_business_date', return_value=date(2026, 10, 15)):
            response = self.client.post(
                f'/api/v1/leases/{self.lease.pk}/terminate/',
                {'end_date': '2026-10-14', 'reason': 'Authorized early move-out'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.TERMINATED)
        self.assertEqual(self.lease.end_date, date(2026, 10, 14))
        self.assertEqual(self.unit.status, Unit.Status.AVAILABLE)

    def test_successor_may_start_day_after_but_not_on_inclusive_final_day(self):
        self.lease.start_date = date(2026, 10, 1)
        self.lease.end_date = date(2026, 10, 14)
        self.lease.save(update_fields=('start_date', 'end_date', 'updated_at'))
        same_day = Lease(
            tenant=self.tenant,
            unit=self.unit,
            reference='L-SAME-DAY',
            start_date=date(2026, 10, 14),
            monthly_rent_minor=100000,
        )
        next_day = Lease(
            tenant=self.tenant,
            unit=self.unit,
            reference='L-NEXT-DAY',
            start_date=date(2026, 10, 15),
            monthly_rent_minor=100000,
        )

        with self.assertRaises(DjangoValidationError):
            same_day.full_clean()
        next_day.full_clean()

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
