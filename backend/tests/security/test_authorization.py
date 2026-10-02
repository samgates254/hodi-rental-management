import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.accounts.models import AccountProfile
from apps.audit.models import AuditLog
from apps.billing.models import LedgerPosting, RentPayment
from apps.leases.models import Lease
from apps.maintenance.models import MaintenanceIssue, MaintenanceRequest, WorkOrder
from apps.notifications.models import Notification
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant


class SecurityWorldMixin:
    password = 'password'

    def make_user(self, username):
        return get_user_model().objects.create_user(username=username, password=self.password)

    def member(self, organization, user, role):
        return OrganizationMembership.objects.create(
            organization=organization,
            user=user,
            role=role,
        )

    def stack(self, organization, tenant, unit_name, reference):
        property_record = Property.objects.create(
            organization=organization,
            name=f'{organization.name} House',
            city='Nairobi',
        )
        building = Building.objects.create(property=property_record, name='Block A')
        unit = Unit.objects.create(building=building, name=unit_name)
        lease = Lease.objects.create(
            tenant=tenant,
            unit=unit,
            reference=reference,
            start_date=date(2026, 1, 1),
            monthly_rent_minor=6500000,
            status=Lease.Status.ACTIVE,
        )
        payment = RentPayment.objects.create(
            lease=lease,
            recorded_by=self.owner_a,
            due_date=date(2026, 10, 1),
            amount_minor=6500000,
            status=RentPayment.Status.PENDING,
        )
        return property_record, building, unit, lease, payment

    def auth(self, user):
        self.client.force_authenticate(user)

    def setUp(self):
        Role = OrganizationMembership.Role
        self.owner_a = self.make_user('owner-a')
        self.owner_b = self.make_user('owner-b')
        self.manager_a = self.make_user('manager-a')
        self.caretaker_a = self.make_user('caretaker-a')
        self.accountant_a = self.make_user('accountant-a')
        self.technician_a = self.make_user('technician-a')
        self.support_a = self.make_user('support-a')
        self.tenant_user_a = self.make_user('tenant-a')
        self.tenant_user_b = self.make_user('tenant-b')
        self.outsider = self.make_user('outsider')
        self.bridge = self.make_user('bridge')
        self.org_a = Organization.objects.create(name='Organization A')
        self.org_b = Organization.objects.create(name='Organization B')
        self.member(self.org_a, self.owner_a, Role.OWNER)
        self.member(self.org_b, self.owner_b, Role.OWNER)
        self.member(self.org_a, self.manager_a, Role.PROPERTY_MANAGER)
        self.member(self.org_a, self.caretaker_a, Role.CARETAKER)
        self.member(self.org_a, self.accountant_a, Role.ACCOUNTANT)
        self.member(self.org_a, self.technician_a, Role.TECHNICIAN)
        self.member(self.org_a, self.support_a, Role.SUPPORT)
        self.member(self.org_a, self.bridge, Role.OWNER)
        self.caretaker_b_membership = self.member(self.org_b, self.bridge, Role.CARETAKER)
        self.tenant_a = Tenant.objects.create(
            user=self.tenant_user_a,
            organization=self.org_a,
            first_name='Amina',
            last_name='A',
            phone_number='+254700000001',
            email='amina@example.com',
            national_id='ID-A-SECRET',
        )
        self.tenant_b = Tenant.objects.create(
            user=self.tenant_user_b,
            organization=self.org_b,
            first_name='Baraka',
            last_name='B',
            phone_number='+254700000002',
            email='baraka@example.com',
            national_id='ID-B-SECRET',
        )
        (
            self.property_a,
            self.building_a,
            self.unit_a,
            self.lease_a,
            self.rent_a,
        ) = self.stack(self.org_a, self.tenant_a, 'A-1', 'LEASE-A')
        (
            self.property_b,
            self.building_b,
            self.unit_b,
            self.lease_b,
            self.rent_b,
        ) = self.stack(self.org_b, self.tenant_b, 'B-1', 'LEASE-B')
        self.issue_a = MaintenanceIssue.objects.create(
            tenant=self.tenant_a,
            unit=self.unit_a,
            title='Leaky tap',
            category='PLUMBING',
            description='Tap drips.',
        )
        self.issue_a.attachments.create(
            file=SimpleUploadedFile('tap.png', b'png-bytes', content_type='image/png'),
            file_name='tap.png',
            content_type='image/png',
            media_type='IMAGE',
        )
        self.request_a = MaintenanceRequest.objects.create(
            unit=self.unit_a,
            tenant=self.tenant_a,
            created_by=self.tenant_user_a,
            title='Burst pipe',
            description='Water on the floor.',
            hazard=4,
            vulnerability=2,
            priority_class=2,
            score_millis=100,
        )
        self.work_a = WorkOrder.objects.create(request=self.request_a, status=WorkOrder.Status.PENDING)
        self.note_a = Notification.objects.create(
            user=self.tenant_user_a,
            organization=self.org_a,
            type=Notification.Type.INVOICE_POSTED,
            title='Invoice for A',
            body='Private to tenant A',
        )
        self.note_b = Notification.objects.create(
            user=self.tenant_user_b,
            organization=self.org_b,
            type=Notification.Type.INVOICE_POSTED,
            title='Invoice for B',
            body='Private to tenant B',
        )
        self.audit_a = AuditLog.objects.create(
            actor=self.owner_a,
            organization=self.org_a,
            action='property.create',
            object_type='Property',
            object_id=str(self.property_a.pk),
        )
        self.audit_b = AuditLog.objects.create(
            actor=self.owner_b,
            organization=self.org_b,
            action='property.create',
            object_type='Property',
            object_id=str(self.property_b.pk),
        )


class CrossOrganizationIsolationTests(SecurityWorldMixin, APITestCase):
    def test_owner_cannot_read_or_write_another_organizations_resources(self):
        self.auth(self.owner_a)
        issue_b = MaintenanceIssue.objects.create(
            tenant=self.tenant_b,
            unit=self.unit_b,
            title='Hidden',
            category='OTHER',
            description='Not for A',
        )
        request_b = MaintenanceRequest.objects.create(
            unit=self.unit_b,
            tenant=self.tenant_b,
            created_by=self.owner_b,
            title='Hidden request',
            description='Other org',
            hazard=2,
            vulnerability=1,
            priority_class=3,
            score_millis=1,
        )
        WorkOrder.objects.create(request=request_b)
        endpoints = [
            ('get', f'/api/v1/properties/{self.property_b.pk}/', None),
            ('patch', f'/api/v1/properties/{self.property_b.pk}/', {'name': 'Stolen'}),
            ('delete', f'/api/v1/properties/{self.property_b.pk}/', None),
            ('get', f'/api/v1/properties/buildings/{self.building_b.pk}/', None),
            ('get', f'/api/v1/properties/units/{self.unit_b.pk}/', None),
            ('get', f'/api/v1/tenants/{self.tenant_b.pk}/', None),
            ('patch', f'/api/v1/tenants/{self.tenant_b.pk}/', {'phone_number': '000'}),
            ('get', f'/api/v1/leases/{self.lease_b.pk}/', None),
            ('post', f'/api/v1/leases/{self.lease_b.pk}/terminate/', {'end_date': '2026-12-01'}),
            ('get', f'/api/v1/billing/payments/{self.rent_b.pk}/', None),
            ('delete', f'/api/v1/billing/payments/{self.rent_b.pk}/', None),
            ('get', f'/api/v1/maintenance/issues/{issue_b.pk}/', None),
            ('get', f'/api/v1/maintenance/requests/{request_b.pk}/', None),
            ('get', f'/api/v1/audit/logs/{self.audit_b.pk}/', None),
            ('get', f'/api/v1/organizations/{self.org_b.pk}/', None),
        ]
        for method, url, body in endpoints:
            response = getattr(self.client, method)(url, body, format='json') if body is not None else getattr(self.client, method)(url)
            self.assertIn(
                response.status_code,
                (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
                f'{method.upper()} {url} leaked or mutated ({response.status_code})',
            )
        self.property_b.refresh_from_db()
        self.rent_b.refresh_from_db()
        self.tenant_b.refresh_from_db()
        self.assertEqual(self.property_b.name, 'Organization B House')
        self.assertEqual(self.rent_b.status, RentPayment.Status.PENDING)
        self.assertEqual(self.tenant_b.phone_number, '+254700000002')
        listed = self.client.get('/api/v1/properties/')
        self.assertEqual([row['id'] for row in listed.data], [self.property_a.pk])

    def test_cross_org_create_bodies_do_not_attach_foreign_records(self):
        self.auth(self.owner_a)
        created = self.client.post('/api/v1/properties/', {
            'organization': self.org_b.pk,
            'name': 'Planted property',
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Property.objects.filter(name='Planted property').exists())

        lease = self.client.post('/api/v1/leases/', {
            'tenant': self.tenant_b.pk,
            'unit': self.unit_b.pk,
            'reference': 'STOLEN',
            'start_date': '2026-02-01',
            'monthly_rent_minor': 1000,
        }, format='json')
        self.assertIn(lease.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST))
        self.assertFalse(Lease.objects.filter(reference='STOLEN').exists())

        self.auth(self.accountant_a)
        invoice = self.client.post('/api/v1/billing/invoices/', {
            'tenant': self.tenant_b.pk,
            'period_start': '2026-10-01',
            'period_end': '2026-10-31',
            'due_date': '2026-10-05',
            'include_rent': False,
        }, format='json')
        self.assertEqual(invoice.status_code, status.HTTP_403_FORBIDDEN)

    def test_multi_org_user_cannot_mutate_a_read_only_organizations_payments(self):
        self.auth(self.bridge)
        readable = self.client.get(f'/api/v1/billing/payments/{self.rent_b.pk}/')
        self.assertEqual(readable.status_code, status.HTTP_200_OK)
        deleted = self.client.delete(f'/api/v1/billing/payments/{self.rent_b.pk}/')
        self.assertEqual(deleted.status_code, status.HTTP_403_FORBIDDEN)
        moved = self.client.patch(f'/api/v1/billing/payments/{self.rent_b.pk}/', {
            'lease': self.lease_a.pk,
            'status': 'PAID',
        }, format='json')
        self.assertEqual(moved.status_code, status.HTTP_403_FORBIDDEN)
        self.rent_b.refresh_from_db()
        self.assertEqual(self.rent_b.lease_id, self.lease_b.pk)
        self.assertEqual(self.rent_b.status, RentPayment.Status.PENDING)

    def test_incrementing_ids_does_not_reveal_foreign_rows(self):
        self.auth(self.tenant_user_a)
        for url in (
            f'/api/v1/leases/{self.lease_b.pk}/',
            f'/api/v1/leases/{self.lease_b.pk + 50}/',
            f'/api/v1/tenants/{self.tenant_b.pk}/',
            f'/api/v1/billing/payments/{self.rent_b.pk}/',
            f'/api/v1/maintenance/issues/{self.issue_a.pk + 99}/',
            f'/api/v1/maintenance/requests/{self.request_a.pk + 99}/',
            f'/api/v1/notifications/{self.note_b.pk}/',
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, url)
        own = self.client.get(f'/api/v1/leases/{self.lease_a.pk}/')
        self.assertEqual(own.status_code, status.HTTP_200_OK)
        self.assertEqual(own.data['tenant_name'], 'Amina A')
        foreign_list = self.client.get('/api/v1/leases/')
        self.assertEqual([row['id'] for row in foreign_list.data], [self.lease_a.pk])


class RoleBoundaryTests(SecurityWorldMixin, APITestCase):
    def test_role_matrix_blocks_unauthorized_actions(self):
        self.auth(self.manager_a)
        self.assertEqual(self.client.get('/api/v1/billing/invoices/').status_code, status.HTTP_200_OK)
        denied_invoice = self.client.post('/api/v1/billing/invoices/', {
            'tenant': self.tenant_a.pk,
            'lease': self.lease_a.pk,
            'period_start': '2026-10-01',
            'period_end': '2026-10-31',
            'due_date': '2026-10-05',
        }, format='json')
        self.assertEqual(denied_invoice.status_code, status.HTTP_403_FORBIDDEN)
        rent_log = self.client.post('/api/v1/billing/payments/', {
            'lease': self.lease_a.pk,
            'due_date': '2026-11-01',
            'amount_minor': 1000,
            'status': 'PENDING',
        }, format='json')
        self.assertEqual(rent_log.status_code, status.HTTP_201_CREATED)
        self.assertEqual(rent_log.data['recorded_by'], self.manager_a.pk)

        self.auth(self.caretaker_a)
        self.assertEqual(self.client.get('/api/v1/billing/invoices/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/v1/billing/ledger-payments/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/v1/leases/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post('/api/v1/billing/payments/', {
            'lease': self.lease_a.pk,
            'due_date': '2026-11-01',
            'amount_minor': 1000,
        }, format='json').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/v1/audit/logs/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post('/api/v1/organizations/staff/', {
            'organization': self.org_a.pk,
            'username': 'new-staff',
            'email': 'new-staff@example.com',
            'first_name': 'New',
            'last_name': 'Staff',
            'role': 'ACCOUNTANT',
            'password': 'A-strong-password-123!',
            'password_confirm': 'A-strong-password-123!',
        }, format='json').status_code, status.HTTP_403_FORBIDDEN)
        tenants = self.client.get('/api/v1/tenants/')
        self.assertEqual(tenants.status_code, status.HTTP_200_OK)
        self.assertEqual(tenants.data[0]['national_id'], '')
        self.assertEqual(tenants.data[0]['phone_number'], '+254700000001')
        self.assertEqual(self.client.get('/api/v1/maintenance/issues/').status_code, status.HTTP_200_OK)

        self.auth(self.accountant_a)
        self.assertEqual(self.client.get('/api/v1/maintenance/requests/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/v1/maintenance/issues/').data, [])
        self.assertEqual(self.client.post('/api/v1/properties/', {
            'organization': self.org_a.pk,
            'name': 'Accountant property',
        }, format='json').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(
            f'/api/v1/leases/{self.lease_a.pk}/activate/',
        ).status_code, status.HTTP_403_FORBIDDEN)
        visible_id = self.client.get('/api/v1/tenants/').data[0]['national_id']
        self.assertEqual(visible_id, 'ID-A-SECRET')
        self.assertEqual(self.client.get('/api/v1/audit/logs/').status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row['id'] for row in self.client.get('/api/v1/audit/logs/').data],
            [self.audit_a.pk],
        )

        self.auth(self.technician_a)
        issues = self.client.get('/api/v1/maintenance/issues/')
        self.assertEqual(issues.status_code, status.HTTP_200_OK)
        self.assertEqual(issues.data, [])
        update = self.client.post(
            f'/api/v1/maintenance/issues/{self.issue_a.pk}/updates/',
            {'status': 'RESOLVED', 'note': 'Fixed without assignment'},
            format='json',
        )
        self.assertEqual(update.status_code, status.HTTP_404_NOT_FOUND)
        attachment = self.issue_a.attachments.get()
        download = self.client.get(
            f'/api/v1/maintenance/issues/{self.issue_a.pk}/attachments/{attachment.pk}/',
        )
        self.assertEqual(download.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get('/api/v1/properties/').status_code, status.HTTP_403_FORBIDDEN)
        requests = self.client.get('/api/v1/maintenance/requests/')
        self.assertEqual(requests.status_code, status.HTTP_200_OK)
        self.assertEqual(requests.data, [])

        self.auth(self.support_a)
        self.assertEqual(self.client.get('/api/v1/properties/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/v1/billing/invoices/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/v1/audit/logs/').status_code, status.HTTP_403_FORBIDDEN)

        self.auth(self.owner_a)
        self.assertEqual(self.client.get('/api/v1/tenants/').data[0]['national_id'], 'ID-A-SECRET')

    def test_inactive_membership_loses_access(self):
        self.caretaker_b_membership.is_active = False
        self.caretaker_b_membership.save(update_fields=('is_active',))
        self.auth(self.bridge)
        # Bridge is still owner of A, so B's payment must disappear from the read scope.
        listing = self.client.get('/api/v1/billing/payments/', {'organization': self.org_b.pk})
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data, [])
        self.assertEqual(
            self.client.get(f'/api/v1/billing/payments/{self.rent_b.pk}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_assignment_cannot_leave_the_organization(self):
        self.auth(self.caretaker_a)
        outsider = self.client.post(
            f'/api/v1/maintenance/requests/{self.request_a.pk}/assign/',
            {'user_id': self.outsider.pk},
            format='json',
        )
        self.assertEqual(outsider.status_code, status.HTTP_400_BAD_REQUEST)
        other_tech = self.client.post(
            f'/api/v1/maintenance/requests/{self.request_a.pk}/assign/',
            {'user_id': self.owner_b.pk},
            format='json',
        )
        self.assertEqual(other_tech.status_code, status.HTTP_400_BAD_REQUEST)
        missing = self.client.post(
            f'/api/v1/maintenance/requests/{self.request_a.pk}/assign/',
            {'user_id': 999999},
            format='json',
        )
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(outsider.data, missing.data)
        self.work_a.refresh_from_db()
        self.assertIsNone(self.work_a.assignee_id)
        assigned = self.client.post(
            f'/api/v1/maintenance/requests/{self.request_a.pk}/assign/',
            {'user_id': self.technician_a.pk},
            format='json',
        )
        self.assertEqual(assigned.status_code, status.HTTP_200_OK)
        self.auth(self.outsider)
        hidden = self.client.get('/api/v1/maintenance/requests/')
        self.assertEqual(hidden.status_code, status.HTTP_403_FORBIDDEN)
        self.auth(self.technician_a)
        visible = self.client.get('/api/v1/maintenance/requests/')
        self.assertEqual([row['id'] for row in visible.data], [self.request_a.pk])

    def test_tenant_cannot_operate_on_another_tenants_records_or_staff_actions(self):
        self.auth(self.tenant_user_a)
        self.assertEqual(
            self.client.patch(f'/api/v1/tenants/{self.tenant_b.pk}/', {'phone_number': '111'}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f'/api/v1/notifications/{self.note_b.pk}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        marked = self.client.post(f'/api/v1/notifications/{self.note_b.pk}/read/')
        self.assertEqual(marked.status_code, status.HTTP_404_NOT_FOUND)
        self.note_b.refresh_from_db()
        self.assertIsNone(self.note_b.read_at)
        own = self.client.post(f'/api/v1/notifications/{self.note_a.pk}/read/')
        self.assertEqual(own.status_code, status.HTTP_200_OK)
        read_all = self.client.post('/api/v1/notifications/read-all/')
        self.assertEqual(read_all.status_code, status.HTTP_200_OK)
        self.note_b.refresh_from_db()
        self.assertIsNone(self.note_b.read_at)
        self.assertEqual(
            self.client.post(f'/api/v1/maintenance/requests/{self.request_a.pk}/complete/').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post(f'/api/v1/maintenance/requests/{self.request_a.pk}/assign/', {'user_id': self.technician_a.pk}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.patch(f'/api/v1/tenants/{self.tenant_a.pk}/', {'national_id': 'CHANGED'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        updated = self.client.patch(f'/api/v1/tenants/{self.tenant_a.pk}/', {'phone_number': '+254711111111'}, format='json')
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data['national_id'], 'ID-A-SECRET')
        self.assertEqual(self.client.get('/api/v1/properties/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/v1/audit/logs/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.post(f'/api/v1/leases/{self.lease_a.pk}/terminate/', {'end_date': '2026-12-01'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )


class FinancialAndAuditIntegrityTests(SecurityWorldMixin, APITestCase):
    def test_allocation_is_scoped_idempotent_and_rejects_bad_amounts(self):
        self.auth(self.accountant_a)
        created = self.client.post('/api/v1/billing/invoices/', {
            'tenant': self.tenant_a.pk,
            'lease': self.lease_a.pk,
            'period_start': '2026-10-01',
            'period_end': '2026-10-31',
            'due_date': '2026-10-05',
            'include_rent': True,
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        invoice_id = created.data['id']
        posted = self.client.post(f'/api/v1/billing/invoices/{invoice_id}/post/')
        self.assertEqual(posted.status_code, status.HTTP_200_OK)
        for payload in (
            {'tenant': self.tenant_a.pk, 'amount_cents': 0, 'received_date': '2026-10-06', 'method': 'CASH'},
            {'tenant': self.tenant_a.pk, 'amount_cents': -5, 'received_date': '2026-10-06', 'method': 'CASH'},
        ):
            rejected = self.client.post('/api/v1/billing/ledger-payments/', payload, format='json')
            self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        foreign = self.client.post('/api/v1/billing/ledger-payments/', {
            'tenant': self.tenant_b.pk,
            'amount_cents': 500,
            'received_date': '2026-10-06',
            'method': 'CASH',
        }, format='json')
        self.assertEqual(foreign.status_code, status.HTTP_403_FORBIDDEN)
        payment = self.client.post('/api/v1/billing/ledger-payments/', {
            'tenant': self.tenant_a.pk,
            'amount_cents': 500,
            'received_date': '2026-10-06',
            'method': 'CASH',
            'external_id': 'ext-once',
            'reference': 'REF-ONCE',
        }, format='json')
        self.assertEqual(payment.status_code, status.HTTP_201_CREATED)
        duplicate = self.client.post('/api/v1/billing/ledger-payments/', {
            'tenant': self.tenant_a.pk,
            'amount_cents': 500,
            'received_date': '2026-10-06',
            'method': 'CASH',
            'external_id': 'ext-once',
        }, format='json')
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        payment_id = payment.data['id']
        first = self.client.post(f'/api/v1/billing/ledger-payments/{payment_id}/allocate/', {
            'policy_id': 'CANONICAL_PRIORITY',
            'policy_version': 2,
        }, format='json')
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        postings = LedgerPosting.objects.filter(payment_id=payment_id).count()
        self.assertGreater(postings, 0)
        second = self.client.post(f'/api/v1/billing/ledger-payments/{payment_id}/allocate/', {
            'policy_id': 'CANONICAL_PRIORITY',
            'policy_version': 2,
        }, format='json')
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(LedgerPosting.objects.filter(payment_id=payment_id).count(), postings)
        self.auth(self.manager_a)
        self.assertEqual(
            self.client.post(f'/api/v1/billing/ledger-payments/{payment_id}/allocate/', {
                'policy_id': 'CANONICAL_PRIORITY',
                'policy_version': 2,
            }, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.auth(self.tenant_user_b)
        self.assertEqual(
            self.client.get(f'/api/v1/billing/invoices/{invoice_id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.auth(self.tenant_user_a)
        own_invoice = self.client.get(f'/api/v1/billing/invoices/{invoice_id}/')
        self.assertEqual(own_invoice.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.post(f'/api/v1/billing/invoices/{invoice_id}/void/').status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_lease_transitions_are_authorized_and_keep_occupancy_consistent(self):
        draft_unit = Unit.objects.create(building=self.building_a, name='A-2')
        draft = Lease.objects.create(
            tenant=self.tenant_a,
            unit=draft_unit,
            reference='DRAFT-A',
            start_date=date(2026, 3, 1),
            monthly_rent_minor=1000,
            status=Lease.Status.DRAFT,
        )
        self.auth(self.tenant_user_a)
        self.assertEqual(self.client.post(f'/api/v1/leases/{draft.pk}/activate/').status_code, status.HTTP_403_FORBIDDEN)
        self.auth(self.owner_b)
        self.assertEqual(self.client.post(f'/api/v1/leases/{draft.pk}/activate/').status_code, status.HTTP_404_NOT_FOUND)
        self.auth(self.owner_a)
        early = self.client.post(f'/api/v1/leases/{draft.pk}/terminate/', {'end_date': '2026-04-01'}, format='json')
        self.assertEqual(early.status_code, status.HTTP_400_BAD_REQUEST)
        activated = self.client.post(f'/api/v1/leases/{draft.pk}/activate/')
        self.assertEqual(activated.status_code, status.HTTP_200_OK)
        draft_unit.refresh_from_db()
        self.assertEqual(draft_unit.status, Unit.Status.OCCUPIED)
        again = self.client.post(f'/api/v1/leases/{draft.pk}/activate/')
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)
        terminated = self.client.post(f'/api/v1/leases/{draft.pk}/terminate/', {'end_date': '2026-04-01'}, format='json')
        self.assertEqual(terminated.status_code, status.HTTP_200_OK)
        draft_unit.refresh_from_db()
        self.assertEqual(draft_unit.status, Unit.Status.AVAILABLE)
        audit = AuditLog.objects.filter(action='lease.activate', object_id=str(draft.pk)).get()
        self.assertEqual(audit.actor_id, self.owner_a.pk)
        self.assertEqual(audit.organization_id, self.org_a.pk)

    def test_clients_cannot_write_audit_logs_or_forge_the_actor(self):
        self.auth(self.tenant_user_a)
        self.assertEqual(self.client.post('/api/v1/audit/logs/', {
            'actor': self.owner_a.pk,
            'action': 'forged',
            'object_type': 'Property',
            'object_id': '1',
        }, format='json').status_code, status.HTTP_403_FORBIDDEN)
        self.auth(self.owner_a)
        for method in ('post', 'put', 'patch', 'delete'):
            response = getattr(self.client, method)(
                f'/api/v1/audit/logs/{self.audit_a.pk}/' if method != 'post' else '/api/v1/audit/logs/',
                {'action': 'forged', 'actor': self.tenant_user_a.pk},
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        created = self.client.post('/api/v1/properties/', {
            'organization': self.org_a.pk,
            'name': 'Audited House',
            'actor': self.tenant_user_a.pk,
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        row = AuditLog.objects.get(action='property.create', object_id=str(created.data['id']))
        self.assertEqual(row.actor_id, self.owner_a.pk)
        self.assertEqual(row.organization_id, self.org_a.pk)
        self.assertIsNotNone(row.created_at)

    def test_closed_maintenance_request_cannot_be_edited(self):
        self.request_a.status = MaintenanceRequest.Status.CLOSED
        self.request_a.save(update_fields=('status', 'updated_at'))
        self.auth(self.owner_a)
        edited = self.client.patch(
            f'/api/v1/maintenance/requests/{self.request_a.pk}/',
            {'title': 'Rewritten'},
            format='json',
        )
        self.assertEqual(edited.status_code, status.HTTP_400_BAD_REQUEST)
        self.request_a.refresh_from_db()
        self.assertEqual(self.request_a.title, 'Burst pipe')


class AccountAndPlatformSecurityTests(SecurityWorldMixin, APITestCase):
    def test_authentication_edges_do_not_leak_or_accept_bad_tokens(self):
        anonymous = self.client.get('/api/v1/properties/')
        self.assertEqual(anonymous.status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials(HTTP_AUTHORIZATION='Token not-a-real-token')
        self.assertEqual(self.client.get('/api/v1/accounts/me/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer abc')
        self.assertEqual(self.client.get('/api/v1/accounts/me/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials(HTTP_AUTHORIZATION='Token')
        self.assertEqual(self.client.get('/api/v1/accounts/me/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials()
        login = self.client.post('/api/v1/accounts/login/', {
            'username': 'owner-a',
            'password': 'wrong-password',
        }, format='json')
        self.assertEqual(login.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn('does not exist', str(login.data).lower())
        token = Token.objects.create(user=self.owner_a)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(self.client.get('/api/v1/accounts/me/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post('/api/v1/accounts/logout/').status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.get('/api/v1/accounts/me/').status_code, status.HTTP_401_UNAUTHORIZED)

    def test_tenant_linking_does_not_grant_another_tenants_data(self):
        signup = self.client.post('/api/v1/accounts/signup/', {
            'account_type': 'TENANT',
            'username': 'new-tenant',
            'email': 'new-tenant@example.com',
            'first_name': 'Nia',
            'last_name': 'Wanjiku',
            'password': 'A-strong-password-123!',
            'password_confirm': 'A-strong-password-123!',
        }, format='json')
        self.assertEqual(signup.status_code, status.HTTP_201_CREATED)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {signup.data['token']}")
        linked = self.client.post('/api/v1/accounts/tenant-organization/', {
            'organization_id': self.org_a.pk,
        }, format='json')
        self.assertEqual(linked.status_code, status.HTTP_200_OK)
        again = self.client.post('/api/v1/accounts/tenant-organization/', {
            'organization_id': self.org_b.pk,
        }, format='json')
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)
        tenants = self.client.get('/api/v1/tenants/')
        self.assertEqual(len(tenants.data), 1)
        self.assertEqual(tenants.data[0]['first_name'], 'Nia')
        self.assertEqual(self.client.get(f'/api/v1/tenants/{self.tenant_a.pk}/').status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get('/api/v1/leases/').data, [])
        self.assertEqual(self.client.get('/api/v1/billing/invoices/').data, [])
        duplicate = self.client.post('/api/v1/accounts/signup/', {
            'account_type': 'TENANT',
            'username': 'new-tenant-2',
            'email': 'new-tenant@example.com',
            'password': 'A-strong-password-123!',
            'password_confirm': 'A-strong-password-123!',
        }, format='json')
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

    def test_owner_account_cannot_self_link_as_a_tenant(self):
        AccountProfile.objects.create(
            user=self.owner_a,
            account_type=AccountProfile.AccountType.OWNER,
            organization=self.org_a,
        )
        self.auth(self.owner_a)
        response = self.client.post('/api/v1/accounts/tenant-organization/', {
            'organization_id': self.org_b.pk,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Tenant.objects.filter(user=self.owner_a, organization=self.org_b).exists())

    def test_organization_directory_exposes_only_id_and_name(self):
        response = self.client.get('/api/v1/accounts/organizations/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data)
        self.assertEqual(set(response.data[0].keys()), {'id', 'name'})

    def test_production_settings_reject_debug_and_placeholder_secrets(self):
        backend = Path(__file__).resolve().parents[2]
        src = backend / 'src'
        base_env = os.environ.copy()
        base_env['PYTHONPATH'] = str(src)
        base_env['DJANGO_SETTINGS_MODULE'] = 'config.settings'
        base_env['DJANGO_ENV'] = 'production'
        debug_env = base_env.copy()
        debug_env['DJANGO_DEBUG'] = 'True'
        debug = subprocess.run(
            [sys.executable, '-c', 'import django; django.setup()'],
            env=debug_env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(debug.returncode, 0)
        self.assertIn('DJANGO_DEBUG must be false', debug.stderr)
        secret_env = base_env.copy()
        secret_env['DJANGO_DEBUG'] = 'False'
        secret_env['DJANGO_SECRET_KEY'] = 'replace-with-a-unique-secret-key'
        secret_env['DJANGO_ALLOWED_HOSTS'] = 'hodi.example'
        secret = subprocess.run(
            [sys.executable, '-c', 'import django; django.setup()'],
            env=secret_env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(secret.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY', secret.stderr)
        self.assertNotIn(secret_env['DJANGO_SECRET_KEY'], secret.stderr)
