from datetime import date
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.leases.models import Lease, LeaseAmendment
from apps.notifications.models import Notification
from apps.organizations.models import Organization
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant
from application.services import leases as lease_services


class ScheduledLeaseExpiryTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username='expiry-owner', password='password')
        self.tenant_user = user_model.objects.create_user(username='expiry-tenant', password='password')
        self.organization = Organization.objects.create(name='Expiry Homes')
        tenant = Tenant.objects.create(
            organization=self.organization,
            user=self.tenant_user,
            first_name='Amina',
            last_name='Otieno',
            phone_number='+254700000020',
        )
        property_record = Property.objects.create(organization=self.organization, name='Expiry Court')
        building = Building.objects.create(property=property_record, name='Block A')
        self.unit = Unit.objects.create(building=building, name='A-1', status=Unit.Status.OCCUPIED)
        self.lease = Lease.objects.create(
            tenant=tenant,
            unit=self.unit,
            reference='EXPIRY-1',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 10, 14),
            monthly_rent_minor=100_000,
            status=Lease.Status.ACTIVE,
        )

    def run_task(self, *, as_of):
        output = StringIO()
        with patch('application.services.leases.rental_business_date', return_value=as_of):
            call_command('expire_due_leases', stdout=output, stderr=output)
        return output.getvalue()

    def test_inclusive_end_date_is_not_expired_on_its_final_day(self):
        output = self.run_task(as_of=date(2026, 10, 14))

        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertIn('processed=0', output)
        self.assertEqual(self.lease.status, Lease.Status.ACTIVE)
        self.assertEqual(self.unit.status, Unit.Status.OCCUPIED)
        self.assertFalse(AuditLog.objects.filter(object_type='Lease', object_id=str(self.lease.pk)).exists())

    def test_expiry_after_inclusive_end_releases_idle_unit_and_records_system_audit(self):
        self.run_task(as_of=date(2026, 10, 15))

        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        audit = AuditLog.objects.get(object_type='Lease', object_id=str(self.lease.pk))
        self.assertEqual(self.lease.status, Lease.Status.EXPIRED)
        self.assertEqual(self.unit.status, Unit.Status.AVAILABLE)
        self.assertIsNone(audit.actor)
        self.assertEqual(audit.metadata['source'], 'scheduled_expiry')

    def test_scheduled_termination_finalizes_once_and_does_not_duplicate_notification(self):
        LeaseAmendment.objects.create(
            lease=self.lease,
            amendment_type=LeaseAmendment.AmendmentType.TERMINATION,
            effective_date=self.lease.end_date,
            reason='Scheduled end of tenancy',
            before_state={'status': Lease.Status.ACTIVE},
            after_state={'status': Lease.Status.ACTIVE},
            created_by=self.owner,
        )

        self.run_task(as_of=date(2026, 10, 15))
        self.run_task(as_of=date(2026, 10, 15))

        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.TERMINATED)
        self.assertEqual(self.unit.status, Unit.Status.AVAILABLE)
        self.assertEqual(
            Notification.objects.filter(user=self.tenant_user, type='LEASE_TERMINATED').count(),
            1,
        )
        self.assertEqual(AuditLog.objects.filter(
            object_type='Lease', object_id=str(self.lease.pk), action='lease.terminate',
        ).count(), 1)

    def test_expiry_keeps_unit_occupied_for_a_valid_successor_lease(self):
        successor_tenant = Tenant.objects.create(
            organization=self.organization,
            first_name='Brian',
            last_name='Mwangi',
            phone_number='+254700000021',
        )
        Lease.objects.create(
            tenant=successor_tenant,
            unit=self.unit,
            reference='EXPIRY-SUCCESSOR',
            start_date=date(2026, 10, 15),
            end_date=date(2027, 10, 14),
            monthly_rent_minor=100_000,
            status=Lease.Status.ACTIVE,
        )

        self.run_task(as_of=date(2026, 10, 15))

        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.EXPIRED)
        self.assertEqual(self.unit.status, Unit.Status.OCCUPIED)

    def test_failed_expiry_rolls_back_and_is_retryable(self):
        with patch('application.services.leases._release_unit_if_idle', side_effect=RuntimeError('injected failure')):
            with self.assertRaises(CommandError):
                self.run_task(as_of=date(2026, 10, 15))

        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.ACTIVE)
        self.assertEqual(self.unit.status, Unit.Status.OCCUPIED)
        self.assertFalse(AuditLog.objects.filter(object_type='Lease', object_id=str(self.lease.pk)).exists())

        output = self.run_task(as_of=date(2026, 10, 15))

        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertIn('processed=1', output)
        self.assertEqual(self.lease.status, Lease.Status.EXPIRED)
        self.assertEqual(self.unit.status, Unit.Status.AVAILABLE)

    def test_one_failed_lease_does_not_block_others_and_reports_retryable_diagnostic(self):
        second_unit = Unit.objects.create(
            building=self.unit.building,
            name='A-2',
            status=Unit.Status.OCCUPIED,
        )
        second_lease = Lease.objects.create(
            tenant=self.lease.tenant,
            unit=second_unit,
            reference='EXPIRY-2',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 10, 13),
            monthly_rent_minor=100_000,
            status=Lease.Status.ACTIVE,
        )
        original_expire_lease = lease_services.expire_lease

        def fail_first_lease(lease, **kwargs):
            if lease.pk == self.lease.pk:
                raise RuntimeError('injected failure detail must not be displayed')
            return original_expire_lease(lease, **kwargs)

        stdout = StringIO()
        stderr = StringIO()
        with patch('application.services.leases.rental_business_date', return_value=date(2026, 10, 15)):
            with patch('application.services.leases.expire_lease', side_effect=fail_first_lease):
                with self.assertRaises(CommandError):
                    call_command('expire_due_leases', stdout=stdout, stderr=stderr)

        diagnostic = stderr.getvalue()
        self.assertIn(f'Lease {self.lease.pk} expiry failed (RuntimeError)', diagnostic)
        self.assertNotIn('injected failure detail', diagnostic)
        self.assertIn('processed=1, failed=1', stdout.getvalue())

        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        second_lease.refresh_from_db()
        second_unit.refresh_from_db()
        self.assertEqual(self.lease.status, Lease.Status.ACTIVE)
        self.assertEqual(self.unit.status, Unit.Status.OCCUPIED)
        self.assertEqual(second_lease.status, Lease.Status.EXPIRED)
        self.assertEqual(second_unit.status, Unit.Status.AVAILABLE)

        retry_output = self.run_task(as_of=date(2026, 10, 15))
        self.lease.refresh_from_db()
        self.unit.refresh_from_db()
        second_lease.refresh_from_db()
        second_unit.refresh_from_db()
        self.assertIn('processed=1, failed=0', retry_output)
        self.assertEqual(self.lease.status, Lease.Status.EXPIRED)
        self.assertEqual(self.unit.status, Unit.Status.AVAILABLE)
        self.assertEqual(second_lease.status, Lease.Status.EXPIRED)
        self.assertEqual(second_unit.status, Unit.Status.AVAILABLE)

        repeated_output = self.run_task(as_of=date(2026, 10, 15))
        self.assertIn('processed=0, failed=0', repeated_output)
        self.assertEqual(
            AuditLog.objects.filter(
                object_type='Lease',
                object_id=str(second_lease.pk),
                action='lease.expire',
            ).count(),
            1,
        )
