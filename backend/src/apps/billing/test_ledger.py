from datetime import date
from collections import Counter
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from apps.audit.models import AuditLog
from apps.billing.models import (
    Charge,
    DocumentStatus,
    Invoice,
    LedgerPosting,
    Payment,
    PaymentAllocation,
    PaymentReversal,
    PaymentReversalAllocation,
)
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

    def create_allocated_payment(self, charge_amounts, payment_amount, method='CASH'):
        self.client.force_authenticate(self.accountant)
        invoice_response = self.client.post(
            '/api/v1/billing/invoices/',
            self.invoice_payload(include_rent=False),
            format='json',
        )
        self.assertEqual(invoice_response.status_code, status.HTTP_201_CREATED)
        invoice_id = invoice_response.data['id']
        for index, amount in enumerate(charge_amounts):
            charge_response = self.client.post('/api/v1/billing/charges/', {
                'invoice': invoice_id,
                'charge_type': 'RENT' if index == 0 else 'WATER',
                'amount_cents': amount,
                'due_date': f'2026-10-{5 + index:02d}',
            }, format='json')
            self.assertEqual(charge_response.status_code, status.HTTP_201_CREATED)
        posted = self.client.post(f'/api/v1/billing/invoices/{invoice_id}/post/')
        self.assertEqual(posted.status_code, status.HTTP_200_OK)
        payment_response = self.client.post('/api/v1/billing/ledger-payments/', {
            'tenant': self.tenant.pk,
            'amount_cents': payment_amount,
            'received_date': '2026-10-06',
            'method': method,
            'reference': f'REVERSAL-{uuid4().hex}',
        }, format='json')
        self.assertEqual(payment_response.status_code, status.HTTP_201_CREATED)
        allocation_response = self.client.post(
            f"/api/v1/billing/ledger-payments/{payment_response.data['id']}/allocate/",
            {'policy_id': 'CANONICAL_PRIORITY', 'policy_version': 2},
            format='json',
        )
        self.assertEqual(allocation_response.status_code, status.HTTP_200_OK)
        return (
            Invoice.objects.get(pk=invoice_id),
            list(Charge.objects.filter(invoice_id=invoice_id).order_by('due_date')),
            Payment.objects.get(pk=payment_response.data['id']),
        )

    def reverse_url(self, payment):
        return f'/api/v1/billing/ledger-payments/{payment.pk}/reverse/'

    def test_generic_rent_allocation_does_not_consume_security_deposit(self):
        self.client.force_authenticate(self.accountant)
        invoice_response = self.client.post(
            '/api/v1/billing/invoices/',
            self.invoice_payload(include_rent=False),
            format='json',
        )
        self.assertEqual(invoice_response.status_code, status.HTTP_201_CREATED)
        invoice = Invoice.objects.get(pk=invoice_response.data['id'])
        rent_response = self.client.post('/api/v1/billing/charges/', {
            'invoice': invoice.pk,
            'charge_type': 'RENT',
            'amount_cents': 10000,
            'due_date': '2026-10-05',
        }, format='json')
        self.assertEqual(rent_response.status_code, status.HTTP_201_CREATED)
        deposit = Charge.objects.create(
            invoice=invoice,
            organization=self.organization,
            tenant=self.tenant,
            charge_type='SECURITY_DEPOSIT',
            amount_cents=50000,
            balance_cents=50000,
            due_date=date(2026, 10, 5),
            lifecycle=DocumentStatus.DRAFT,
            currency='KES',
        )
        posted = self.client.post(f'/api/v1/billing/invoices/{invoice.pk}/post/')
        self.assertEqual(posted.status_code, status.HTTP_200_OK)

        payment_response = self.client.post('/api/v1/billing/ledger-payments/', {
            'tenant': self.tenant.pk,
            'amount_cents': 10000,
            'received_date': '2026-10-06',
            'method': 'CASH',
            'reference': 'RENT-ONLY-WITH-DEPOSIT',
        }, format='json')
        self.assertEqual(payment_response.status_code, status.HTTP_201_CREATED)
        allocation_response = self.client.post(
            f"/api/v1/billing/ledger-payments/{payment_response.data['id']}/allocate/",
            {'policy_id': 'CANONICAL_PRIORITY', 'policy_version': 2},
            format='json',
        )
        self.assertEqual(allocation_response.status_code, status.HTTP_200_OK)

        deposit.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(deposit.balance_cents, 50000)
        self.assertEqual(invoice.balance_cents, 50000)
        self.assertEqual(
            list(PaymentAllocation.objects.filter(payment_id=payment_response.data['id']).values_list(
                'charge__charge_type', flat=True,
            )),
            ['RENT'],
        )
        self.assertFalse(LedgerPosting.objects.filter(
            payment_id=payment_response.data['id'], account='2030',
        ).exists())

    def test_unauthenticated_invoice_list_is_rejected(self):
        response = self.client.get('/api/v1/billing/invoices/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rent_invoice_generation_retry_returns_same_invoice(self):
        self.client.force_authenticate(self.accountant)
        first = self.client.post('/api/v1/billing/invoices/', self.invoice_payload(), format='json')
        retry = self.client.post('/api/v1/billing/invoices/', self.invoice_payload(), format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(retry.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data['id'], retry.data['id'])
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(Charge.objects.filter(charge_type='RENT').count(), 1)
        changed_period = self.client.patch(
            f"/api/v1/billing/invoices/{first.data['id']}/",
            {'period_start': '2026-10-02'},
            format='json',
        )
        self.assertEqual(changed_period.status_code, status.HTTP_400_BAD_REQUEST)

    def test_landlord_and_tenant_see_same_invoice_total_and_separate_balance(self):
        self.client.force_authenticate(self.accountant)
        created = self.client.post('/api/v1/billing/invoices/', self.invoice_payload(
            include_rent=False,
        ), format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        invoice_id = created.data['id']

        charge = self.client.post('/api/v1/billing/charges/', {
            'invoice': invoice_id,
            'charge_type': 'RENT',
            'amount_cents': 5_000_000,
            'due_date': '2026-10-05',
            'description': 'October rent',
        }, format='json')
        self.assertEqual(charge.status_code, status.HTTP_201_CREATED)
        posted = self.client.post(f'/api/v1/billing/invoices/{invoice_id}/post/')
        self.assertEqual(posted.status_code, status.HTTP_200_OK)
        self.assertEqual(posted.data['total_cents'], 5_000_000)
        self.assertEqual(posted.data['paid_cents'], 0)
        self.assertEqual(posted.data['balance_cents'], 5_000_000)
        invoice = Invoice.objects.get(pk=invoice_id)
        self.assertEqual(invoice.total_cents, 5_000_000)
        self.assertEqual(invoice.charges.get().amount_cents, 5_000_000)
        self.assertEqual(invoice.currency, 'KES')

        payment = self.client.post('/api/v1/billing/ledger-payments/', {
            'tenant': self.tenant.pk,
            'amount_cents': 1_613_000,
            'received_date': '2026-10-06',
            'method': 'CASH',
            'reference': 'PARTIAL-16130',
        }, format='json')
        self.assertEqual(payment.status_code, status.HTTP_201_CREATED)
        allocated = self.client.post(
            f"/api/v1/billing/ledger-payments/{payment.data['id']}/allocate/",
            {'policy_id': 'CANONICAL_PRIORITY', 'policy_version': 2},
            format='json',
        )
        self.assertEqual(allocated.status_code, status.HTTP_200_OK)
        self.assertEqual(allocated.data['allocated_cents'], 1_613_000)

        invoice.refresh_from_db()
        self.assertEqual(invoice.total_cents, 5_000_000)
        self.assertEqual(invoice.balance_cents, 3_387_000)
        self.assertEqual(invoice.charges.get().balance_cents, 3_387_000)

        landlord_list = self.client.get('/api/v1/billing/invoices/')
        landlord_detail = self.client.get(f'/api/v1/billing/invoices/{invoice_id}/')
        self.assertEqual(landlord_list.status_code, status.HTTP_200_OK)
        self.assertEqual(landlord_detail.status_code, status.HTTP_200_OK)
        landlord_invoice = next(row for row in landlord_list.data if row['id'] == invoice_id)

        self.client.force_authenticate(self.tenant_user)
        tenant_list = self.client.get('/api/v1/billing/invoices/')
        tenant_detail = self.client.get(f'/api/v1/billing/invoices/{invoice_id}/')
        self.assertEqual(tenant_list.status_code, status.HTTP_200_OK)
        self.assertEqual(tenant_detail.status_code, status.HTTP_200_OK)
        tenant_invoice = next(row for row in tenant_list.data if row['id'] == invoice_id)

        for response_invoice in (landlord_invoice, landlord_detail.data, tenant_invoice, tenant_detail.data):
            self.assertEqual(response_invoice['id'], invoice_id)
            self.assertEqual(response_invoice['tenant'], self.tenant.pk)
            self.assertEqual(response_invoice['organization'], self.organization.pk)
            self.assertEqual(response_invoice['currency'], 'KES')
            self.assertEqual(response_invoice['total_cents'], 5_000_000)
            self.assertEqual(response_invoice['paid_cents'], 1_613_000)
            self.assertEqual(response_invoice['balance_cents'], 3_387_000)

        other_user = get_user_model().objects.create_user(username='other-tenant', password='password')
        other_tenant = Tenant.objects.create(
            organization=self.organization,
            user=other_user,
            first_name='Other',
            last_name='Tenant',
        )
        other_invoice = Invoice.objects.create(
            organization=self.organization,
            tenant=other_tenant,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            due_date=date(2026, 10, 5),
            status=DocumentStatus.POSTED,
            total_cents=2_000_000,
            balance_cents=2_000_000,
        )
        hidden = self.client.get(f'/api/v1/billing/invoices/{other_invoice.pk}/')
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)

    def test_invoice_total_sums_itemized_charges_in_minor_units(self):
        self.client.force_authenticate(self.accountant)
        created = self.client.post('/api/v1/billing/invoices/', self.invoice_payload(
            include_rent=False,
        ), format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        invoice_id = created.data['id']

        for charge_type, amount_cents in (('WATER', 1_613_001), ('SERVICE_CHARGE', 25_050)):
            response = self.client.post('/api/v1/billing/charges/', {
                'invoice': invoice_id,
                'charge_type': charge_type,
                'amount_cents': amount_cents,
                'due_date': '2026-10-05',
            }, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        invoice = self.client.get(f'/api/v1/billing/invoices/{invoice_id}/')
        self.assertEqual(invoice.data['total_cents'], 1_638_051)
        self.assertEqual(
            sum(charge['amount_cents'] for charge in invoice.data['charges']),
            invoice.data['total_cents'],
        )
        self.assertEqual(invoice.data['currency'], 'KES')

    def test_invoice_creation_rolls_back_after_charge_persistence_failure(self):
        self.client.force_authenticate(self.accountant)
        with patch('application.services.billing.recompute_invoice_totals', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                self.client.post('/api/v1/billing/invoices/', self.invoice_payload(), format='json')
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(Charge.objects.count(), 0)

    def test_generation_key_cannot_be_reused_for_another_period(self):
        self.client.force_authenticate(self.accountant)
        payload = self.invoice_payload(generation_key='manual-cycle:october')
        first = self.client.post('/api/v1/billing/invoices/', payload, format='json')
        second = self.client.post('/api/v1/billing/invoices/', {
            **payload, 'period_start': '2026-10-02', 'period_end': '2026-11-01',
        }, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Invoice.objects.count(), 1)

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

    def test_full_payment_reversal_restores_invoice_and_posts_auditable_offsets(self):
        invoice, charges, payment = self.create_allocated_payment([10_000], 10_000)
        original_postings = list(payment.postings.all())
        original_allocations = list(payment.allocations.all())

        response = self.client.post(self.reverse_url(payment), {
            'reason': 'Bank transfer was returned by the bank',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Payment.Status.REVERSED)
        self.assertEqual(response.data['reference'], payment.reference)
        self.assertEqual(response.data['reversal']['status'], PaymentReversal.Status.REVERSED)
        self.assertEqual(response.data['reversal']['amount_cents'], 10_000)
        payment.refresh_from_db()
        invoice.refresh_from_db()
        charges[0].refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REVERSED)
        self.assertEqual(invoice.total_cents, 10_000)
        self.assertEqual(invoice.balance_cents, 10_000)
        self.assertEqual(charges[0].balance_cents, 10_000)
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 1)
        self.assertEqual(PaymentReversalAllocation.objects.count(), 1)
        self.assertEqual(LedgerPosting.objects.filter(payment=payment).count(), 4)
        reversed_postings = LedgerPosting.objects.filter(reversal__payment=payment)
        expected = Counter(
            (row.account, 'CREDIT' if row.direction == 'DEBIT' else 'DEBIT', row.amount_cents)
            for row in original_postings
        )
        actual = Counter((row.account, row.direction, row.amount_cents) for row in reversed_postings)
        self.assertEqual(actual, expected)
        self.assertTrue(AuditLog.objects.filter(
            action='payment.reverse', object_id=str(response.data['reversal']['id']), actor=self.accountant,
        ).exists())
        self.assertTrue(Notification.objects.filter(user=self.tenant_user, type='PAYMENT_REVERSED').exists())
        self.assertEqual(len(original_allocations), 1)

    def test_reversal_restores_multiple_charge_allocations(self):
        invoice, charges, payment = self.create_allocated_payment([4_000, 6_000], 10_000)
        self.assertEqual(payment.allocations.count(), 2)
        self.assertTrue(all(charge.balance_cents == 0 for charge in charges))

        response = self.client.post(self.reverse_url(payment), {'reason': 'Receipt was duplicated'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['reversal']['allocations'].__len__(), 2)
        for charge in charges:
            charge.refresh_from_db()
            self.assertEqual(charge.balance_cents, charge.amount_cents)
        invoice.refresh_from_db()
        self.assertEqual(invoice.balance_cents, 10_000)

    def test_partly_allocated_reversal_restores_charge_and_removes_unallocated_credit(self):
        invoice, charges, payment = self.create_allocated_payment([1_000], 1_500)
        self.assertEqual(payment.allocated_cents, 1_000)
        self.assertEqual(payment.overpayment_cents, 500)

        response = self.client.post(self.reverse_url(payment), {'reason': 'Cash receipt was rescinded'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['reversal']['amount_cents'], 1_500)
        payment.refresh_from_db()
        charges[0].refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(payment.allocated_cents, 1_000)
        self.assertEqual(payment.overpayment_cents, 500)
        self.assertEqual(charges[0].balance_cents, 1_000)
        self.assertEqual(invoice.balance_cents, 1_000)
        self.assertTrue(LedgerPosting.objects.filter(
            reversal__payment=payment, account='2020', direction='DEBIT', amount_cents=500,
        ).exists())

        self.client.force_authenticate(self.tenant_user)
        statement = self.client.get('/api/v1/billing/statements/me/', {
            'from': '2026-10-01', 'to': '2026-10-31',
        })
        self.assertEqual(statement.status_code, status.HTTP_200_OK)
        self.assertEqual(statement.data['outstanding_cents'], 1_000)
        self.assertEqual(statement.data['credit_cents'], 0)
        self.assertEqual(statement.data['current_balance_cents'], 1_000)
        reversal_lines = [line for line in statement.data['lines'] if line['kind'] == 'payment_reversal']
        self.assertEqual(len(reversal_lines), 1)
        self.assertEqual(reversal_lines[0]['debit_cents'], 1_500)

    def test_identical_reversal_is_idempotent_and_different_reason_is_rejected(self):
        _invoice, _charges, payment = self.create_allocated_payment([2_000], 2_000)
        body = {'reason': 'Duplicate cash receipt'}
        first = self.client.post(self.reverse_url(payment), body, format='json')
        posting_count = LedgerPosting.objects.filter(payment=payment).count()
        second = self.client.post(self.reverse_url(payment), body, format='json')
        different = self.client.post(self.reverse_url(payment), {'reason': 'Changed reason'}, format='json')

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data['reversal']['id'], first.data['reversal']['id'])
        self.assertEqual(different.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(PaymentReversal.objects.filter(payment=payment).count(), 1)
        self.assertEqual(LedgerPosting.objects.filter(payment=payment).count(), posting_count)

    def test_partial_amount_missing_reason_and_invalid_payment_are_rejected(self):
        _invoice, _charges, payment = self.create_allocated_payment([2_000], 2_000)
        partial = self.client.post(self.reverse_url(payment), {
            'reason': 'Attempted partial reversal', 'amount_cents': 1_000,
        }, format='json')
        missing_reason = self.client.post(self.reverse_url(payment), {'reason': '   '}, format='json')
        invalid = self.client.post(
            '/api/v1/billing/ledger-payments/00000000-0000-0000-0000-000000000000/reverse/',
            {'reason': 'Not a real payment'}, format='json',
        )
        self.assertEqual(partial.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(missing_reason.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(PaymentReversal.objects.filter(payment=payment).exists())

    def test_voided_payment_cannot_be_reversed(self):
        _invoice, _charges, payment = self.create_allocated_payment([2_000], 2_000)
        Payment.objects.filter(pk=payment.pk).update(status=Payment.Status.VOIDED)
        response = self.client.post(self.reverse_url(payment), {'reason': 'Voided receipt'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(PaymentReversal.objects.filter(payment=payment).exists())

    def test_reversal_requires_billing_write_permission_and_organization_scope(self):
        _invoice, _charges, payment = self.create_allocated_payment([2_000], 2_000)
        self.client.force_authenticate(self.manager)
        manager_denied = self.client.post(self.reverse_url(payment), {'reason': 'No authority'}, format='json')
        self.client.force_authenticate(self.tenant_user)
        tenant_denied = self.client.post(self.reverse_url(payment), {'reason': 'Tenant attempt'}, format='json')
        self.client.force_authenticate(self.outsider)
        cross_org_hidden = self.client.post(self.reverse_url(payment), {'reason': 'Other org'}, format='json')

        self.assertEqual(manager_denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(tenant_denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(cross_org_hidden.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(PaymentReversal.objects.filter(payment=payment).exists())

    def test_mpesa_reversal_request_stays_unresolved_without_provider_evidence(self):
        invoice, charges, payment = self.create_allocated_payment([2_000], 2_000, method='MPESA')
        before_postings = payment.postings.count()
        response = self.client.post(self.reverse_url(payment), {
            'reason': 'Tenant reports a provider-side reversal; receipt needs independent review',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['status'], Payment.Status.ALLOCATED)
        self.assertEqual(response.data['reversal']['status'], PaymentReversal.Status.REVIEW_REQUIRED)
        self.assertEqual(payment.postings.count(), before_postings)
        self.assertEqual(PaymentReversalAllocation.objects.count(), 0)
        charges[0].refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(charges[0].balance_cents, 0)
        self.assertEqual(invoice.balance_cents, 0)
        self.assertTrue(AuditLog.objects.filter(action='payment.reversal_review_required').exists())


@skipUnless(connection.vendor == 'postgresql', 'Concurrent row-lock test requires PostgreSQL.')
class PaymentReversalConcurrencyTests(TransactionTestCase):
    def test_two_identical_concurrent_reversals_create_one_compensation(self):
        user_model = get_user_model()
        actor = user_model.objects.create_user(username='reversal-concurrency', password='test')
        organization = Organization.objects.create(name='Concurrency Homes')
        tenant = Tenant.objects.create(
            organization=organization,
            first_name='Concurrent',
            last_name='Tenant',
            phone_number='+254700000089',
        )
        invoice = Invoice.objects.create(
            organization=organization,
            tenant=tenant,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            due_date=date(2026, 10, 5),
            status=DocumentStatus.POSTED,
            total_cents=3_000,
            balance_cents=0,
        )
        charge = Charge.objects.create(
            invoice=invoice,
            organization=organization,
            tenant=tenant,
            charge_type='RENT',
            amount_cents=3_000,
            balance_cents=0,
            due_date=date(2026, 10, 5),
            lifecycle=DocumentStatus.POSTED,
        )
        payment = Payment.objects.create(
            organization=organization,
            tenant=tenant,
            amount_cents=3_000,
            allocated_cents=3_000,
            received_date=date(2026, 10, 6),
            execution_timestamp=timezone.now(),
            method=Payment.Method.CASH,
            status=Payment.Status.ALLOCATED,
            recorded_by=actor,
        )
        PaymentAllocation.objects.create(
            payment=payment,
            charge=charge,
            amount_cents=3_000,
            policy_id='CANONICAL_PRIORITY',
            policy_version=2,
        )
        LedgerPosting.objects.create(payment=payment, account='2000', direction='DEBIT', amount_cents=3_000)
        LedgerPosting.objects.create(payment=payment, account='2010', direction='CREDIT', amount_cents=3_000)
        payment_id = payment.pk
        actor_id = actor.pk

        def reverse_in_own_connection():
            from application.services.billing import reverse_payment

            user = get_user_model().objects.get(pk=actor_id)
            target = Payment.objects.get(pk=payment_id)
            return reverse_payment(target, reason='Concurrent duplicate', actor=user).pk

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: reverse_in_own_connection(), range(2)))
        self.assertEqual(results[0], results[1])
        payment.refresh_from_db()
        self.assertEqual(PaymentReversal.objects.filter(payment=payment).count(), 1)
        self.assertEqual(LedgerPosting.objects.filter(payment=payment).count(), 4)
