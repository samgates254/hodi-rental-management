from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.billing.models import Charge, DocumentStatus, Invoice, Payment
from apps.leases.models import Lease
from apps.notifications.models import Notification
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant
from engines.proration.facade import prorate_move_in


class LedgerApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username='owner', password='password')
        self.manager = user_model.objects.create_user(username='manager', password='password')
        self.accountant = user_model.objects.create_user(username='accountant', password='password')
        self.caretaker = user_model.objects.create_user(username='caretaker', password='password')
        self.tenant_user = user_model.objects.create_user(username='tenant', password='password')
        self.outsider = user_model.objects.create_user(username='outsider', password='password')
        self.organization = Organization.objects.create(name='Rongai Homes')
        self.other = Organization.objects.create(name='Other Homes')
        for user, role in (
            (self.owner, OrganizationMembership.Role.OWNER),
            (self.manager, OrganizationMembership.Role.PROPERTY_MANAGER),
            (self.accountant, OrganizationMembership.Role.ACCOUNTANT),
            (self.caretaker, OrganizationMembership.Role.CARETAKER),
        ):
            OrganizationMembership.objects.create(organization=self.organization, user=user, role=role)
        OrganizationMembership.objects.create(
            organization=self.other,
            user=self.outsider,
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
        unit = Unit.objects.create(building=building, name='A-1')
        self.lease = Lease.objects.create(
            tenant=self.tenant,
            unit=unit,
            reference='L-1',
            start_date=date(2026, 10, 15),
            monthly_rent_minor=100000,
            status=Lease.Status.ACTIVE,
        )

    def invoice_payload(self, **overrides):
        payload = {
            'tenant': self.tenant.pk,
            'lease': self.lease.pk,
            'period_start': '2026-10-01',
            'period_end': '2026-10-31',
            'due_date': '2026-10-05',
        }
        payload.update(overrides)
        return payload

    def test_unauthenticated_invoice_list_is_rejected(self):
        response = self.client.get('/api/v1/billing/invoices/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_prorated_rent_posts_allocates_and_isolates_organizations(self):
        self.client.force_authenticate(self.accountant)
        created = self.client.post('/api/v1/billing/invoices/', self.invoice_payload(), format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        expected = prorate_move_in(100000, date(2026, 10, 15)).charge_cents
        self.assertEqual(created.data['charges'][0]['amount_cents'], expected)
        self.assertEqual(created.data['charges'][0]['charge_type'], 'RENT')
        self.assertEqual(created.data['status'], 'DRAFT')

        invoice_id = created.data['id']
        posted = self.client.post(f'/api/v1/billing/invoices/{invoice_id}/post/')
        self.assertEqual(posted.status_code, status.HTTP_200_OK)
        self.assertEqual(posted.data['status'], 'POSTED')
        self.assertEqual(posted.data['balance_cents'], expected)
        self.assertTrue(Notification.objects.filter(user=self.tenant_user, type='INVOICE_POSTED').exists())
        self.assertTrue(AuditLog.objects.filter(action='invoice.post', object_id=str(invoice_id)).exists())

        water = self.client.post('/api/v1/billing/charges/', {
            'invoice': invoice_id,
            'charge_type': 'WATER',
            'amount_cents': 3000,
            'due_date': '2026-10-01',
        }, format='json')
        self.assertEqual(water.status_code, status.HTTP_400_BAD_REQUEST)

        draft = self.client.post('/api/v1/billing/invoices/', self.invoice_payload(
            include_rent=False,
            period_start='2026-11-01',
            period_end='2026-11-30',
            due_date='2026-11-05',
        ), format='json')
        self.assertEqual(draft.status_code, status.HTTP_201_CREATED)
        water = self.client.post('/api/v1/billing/charges/', {
            'invoice': draft.data['id'],
            'charge_type': 'WATER',
            'amount_cents': 3000,
            'due_date': '2026-10-01',
            'period_start': '2026-10-01',
        }, format='json')
        self.assertEqual(water.status_code, status.HTTP_201_CREATED)
        posted_water = self.client.post(f"/api/v1/billing/invoices/{draft.data['id']}/post/")
        self.assertEqual(posted_water.status_code, status.HTTP_200_OK)

        paid = self.client.post('/api/v1/billing/ledger-payments/', {
            'tenant': self.tenant.pk,
            'amount_cents': 80000,
            'received_date': '2026-11-02',
            'method': 'MPESA',
            'reference': 'MPESA-1',
            'external_id': 'txn-1',
        }, format='json')
        self.assertEqual(paid.status_code, status.HTTP_201_CREATED)
        payment_id = paid.data['id']

        self.client.force_authenticate(self.manager)
        denied = self.client.post(f'/api/v1/billing/ledger-payments/{payment_id}/allocate/', {
            'policy_id': 'CANONICAL_PRIORITY',
            'policy_version': 2,
        }, format='json')
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.caretaker)
        caretaker_denied = self.client.get('/api/v1/billing/invoices/')
        self.assertEqual(caretaker_denied.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.accountant)
        allocated = self.client.post(f'/api/v1/billing/ledger-payments/{payment_id}/allocate/', {
            'policy_id': 'CANONICAL_PRIORITY',
            'policy_version': 2,
        }, format='json')
        self.assertEqual(allocated.status_code, status.HTTP_200_OK)
        self.assertEqual(allocated.data['allocated_cents'] + allocated.data['overpayment_cents'], 80000)
        self.assertGreater(allocated.data['overpayment_cents'], 0)
        accounts = {row['account'] for row in allocated.data['postings']}
        self.assertIn('2020', accounts)
        self.assertNotIn('2030', accounts)
        self.assertTrue(AuditLog.objects.filter(action='payment.allocate', object_id=str(payment_id)).exists())
        self.assertTrue(Notification.objects.filter(user=self.tenant_user, type='PAYMENT_RECEIVED').exists())

        water_charge = Charge.objects.get(charge_type='WATER')
        rent_charge = Charge.objects.get(charge_type='RENT', lifecycle=DocumentStatus.POSTED)
        self.assertEqual(water_charge.balance_cents, 0)
        self.assertLess(rent_charge.balance_cents, rent_charge.amount_cents)

        self.client.force_authenticate(self.outsider)
        hidden = self.client.get('/api/v1/billing/invoices/')
        self.assertEqual(hidden.status_code, status.HTTP_200_OK)
        self.assertEqual(hidden.data, [])
        missing = self.client.get(f'/api/v1/billing/invoices/{invoice_id}/')
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(self.tenant_user)
        own = self.client.get('/api/v1/billing/invoices/')
        self.assertEqual(own.status_code, status.HTTP_200_OK)
        self.assertEqual(len(own.data), 2)
        own_payment = self.client.get(f'/api/v1/billing/ledger-payments/{payment_id}/')
        self.assertEqual(own_payment.status_code, status.HTTP_200_OK)

        duplicate = self.client.post('/api/v1/billing/ledger-payments/', {
            'tenant': self.tenant.pk,
            'amount_cents': 100,
            'received_date': '2026-11-03',
            'method': 'CASH',
            'external_id': 'txn-1',
        }, format='json')
        self.assertEqual(duplicate.status_code, status.HTTP_403_FORBIDDEN)

    def test_void_posted_invoice_without_allocations(self):
        self.client.force_authenticate(self.owner)
        created = self.client.post('/api/v1/billing/invoices/', self.invoice_payload(
            include_rent=False,
            period_start='2026-12-01',
            period_end='2026-12-31',
        ), format='json')
        self.client.post('/api/v1/billing/charges/', {
            'invoice': created.data['id'],
            'charge_type': 'OTHER',
            'amount_cents': 500,
            'due_date': '2026-12-05',
        }, format='json')
        self.client.post(f"/api/v1/billing/invoices/{created.data['id']}/post/")
        voided = self.client.post(f"/api/v1/billing/invoices/{created.data['id']}/void/")
        self.assertEqual(voided.status_code, status.HTTP_200_OK)
        self.assertEqual(voided.data['status'], 'VOIDED')
        self.assertEqual(voided.data['balance_cents'], 0)
        invoice = Invoice.objects.get(pk=created.data['id'])
        self.assertTrue(invoice.charges.filter(lifecycle=DocumentStatus.VOIDED).exists())

    def test_delinquency_uses_posted_balances(self):
        self.client.force_authenticate(self.accountant)
        created = self.client.post('/api/v1/billing/invoices/', self.invoice_payload(include_rent=False), format='json')
        self.client.post('/api/v1/billing/charges/', {
            'invoice': created.data['id'],
            'charge_type': 'RENT',
            'amount_cents': 4000,
            'due_date': '2026-10-01',
        }, format='json')
        self.client.post(f"/api/v1/billing/invoices/{created.data['id']}/post/")
        response = self.client.get('/api/v1/billing/delinquency/', {
            'tenant': self.tenant.pk,
            'as_of': '2026-10-10',
            'grace_days': 0,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'DELINQUENT')
        self.assertEqual(response.data['delinquent_cents'], 4000)
        self.assertFalse(Payment.objects.exists())
