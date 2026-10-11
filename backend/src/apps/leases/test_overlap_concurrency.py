import threading
import time
from datetime import date
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import connection, connections, transaction
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.leases.models import Lease
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant


@skipUnless(connection.vendor == 'postgresql', 'Row-lock concurrency requires PostgreSQL.')
class LeaseOverlapConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username='lease-lock-owner', password='test')
        self.organization = Organization.objects.create(name='Lease Lock Homes')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
        )
        property_record = Property.objects.create(organization=self.organization, name='Lock Court')
        building = Building.objects.create(property=property_record, name='Block A')
        self.unit = Unit.objects.create(building=building, name='A-1')
        self.tenants = [
            Tenant.objects.create(
                organization=self.organization,
                first_name=f'Tenant {index}',
                last_name='Test',
                phone_number=f'+25470000000{index}',
            )
            for index in (1, 2)
        ]

    def test_concurrent_overlapping_creates_allow_only_one_lease(self):
        lock_held = threading.Event()
        release_holder = threading.Event()
        competitor_started = threading.Event()
        holder_errors = []
        api_results = []

        def hold_unit_and_create_first_lease():
            try:
                with transaction.atomic():
                    Unit.objects.select_for_update().get(pk=self.unit.pk)
                    lock_held.set()
                    if not release_holder.wait(timeout=10):
                        raise TimeoutError('Timed out waiting to release the unit lock.')
                    lease = Lease(
                        tenant=self.tenants[0], unit=self.unit, reference='LOCK-HOLDER',
                        start_date=date(2026, 1, 1), monthly_rent_minor=100000,
                    )
                    lease.full_clean()
                    lease.save()
            except BaseException as error:
                holder_errors.append(error)
            finally:
                connection.close()

        def create_conflicting_lease_through_api():
            try:
                competitor_started.set()
                client = APIClient()
                client.force_authenticate(self.owner)
                response = client.post('/api/v1/leases/', {
                    'tenant': self.tenants[1].pk,
                    'unit': self.unit.pk,
                    'reference': 'LOCK-API',
                    'start_date': date(2026, 1, 1).isoformat(),
                    'monthly_rent_minor': 100000,
                }, format='json')
                api_results.append(response.status_code)
            except BaseException as error:
                api_results.append(error)
            finally:
                connection.close()

        holder = threading.Thread(target=hold_unit_and_create_first_lease)
        holder.start()
        self.assertTrue(lock_held.wait(timeout=5), 'Holder did not acquire the unit lock.')
        contender = threading.Thread(target=create_conflicting_lease_through_api)
        contender.start()
        try:
            self.assertTrue(competitor_started.wait(timeout=5), 'Conflicting API transaction did not start.')
            deadline = time.monotonic() + 8
            observed_lock_wait = False
            while time.monotonic() < deadline:
                with connections['default'].cursor() as cursor:
                    cursor.execute(
                        "SELECT query FROM pg_stat_activity "
                        "WHERE datname = current_database() "
                        "AND pid <> pg_backend_pid() "
                        "AND wait_event_type = 'Lock'",
                    )
                    waiting_queries = [row[0] for row in cursor.fetchall()]
                if any('FOR UPDATE' in query.upper() for query in waiting_queries):
                    observed_lock_wait = True
                    break
                time.sleep(0.025)
            self.assertTrue(observed_lock_wait, 'API transaction never waited on the held PostgreSQL row lock.')
        finally:
            release_holder.set()
        holder.join(timeout=10)
        contender.join(timeout=10)

        self.assertFalse(holder.is_alive(), 'Lock holder did not finish.')
        self.assertFalse(contender.is_alive(), 'Conflicting API transaction did not finish.')
        self.assertEqual(holder_errors, [])
        self.assertEqual(api_results, [400])
        self.assertEqual(Lease.objects.filter(unit=self.unit).count(), 1)
