from datetime import date
from collections import Counter
from threading import Barrier
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase
from unittest.mock import patch

from apps.audit.models import AuditLog
from apps.billing.models import (
    Charge,
    ChargeJournalEntry,
    DocumentStatus,
    Invoice,
    LedgerPosting,
    MAX_MONEY_CENTS,
    Payment,
    PaymentAllocation,
    PaymentReversal,
    PaymentReversalAllocation,
    RentPayment,
)
from apps.leases.models import Lease, RentSchedule
from apps.notifications.models import Notification
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant
from application.services.billing import (
    allocate_payment, record_manual_receipt, record_payment,
    record_verified_mpesa_payment, rent_charge_amount,
)
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
        reference = f'REVERSAL-{uuid4().hex}'
        if method == Payment.Method.MPESA:
            # The staff payment API must not manufacture a provider payment.
            # Build this historical settlement through the internal service so
            # the reversal test remains focused on its provider-review rule.
            receipt = f'TEST-MPESA-{uuid4().hex.upper()}'
            payment = record_verified_mpesa_payment(
                tenant=self.tenant,
                amount_cents=payment_amount,
                received_date=date(2026, 10, 6),
                reference=receipt,
                external_id=receipt,
                actor=self.accountant,
            )
            payment = allocate_payment(
                payment,
                policy_id='CANONICAL_PRIORITY',
                policy_version=2,
                actor=self.accountant,
            )
        else:
            payment_response = self.client.post('/api/v1/billing/ledger-payments/', {
                'tenant': self.tenant.pk,
                'amount_cents': payment_amount,
                'received_date': '2026-10-06',
                'method': method,
                'reference': reference,
            }, format='json')
            self.assertEqual(payment_response.status_code, status.HTTP_201_CREATED)
            allocation_response = self.client.post(
                f"/api/v1/billing/ledger-payments/{payment_response.data['id']}/allocate/",
                {'policy_id': 'CANONICAL_PRIORITY', 'policy_version': 2},
                format='json',
            )
            self.assertEqual(allocation_response.status_code, status.HTTP_200_OK)
            payment = Payment.objects.get(pk=payment_response.data['id'])
        return (
            Invoice.objects.get(pk=invoice_id),
            list(Charge.objects.filter(invoice_id=invoice_id).order_by('due_date')),
            payment,
        )

    def reverse_url(self, payment):
        return f'/api/v1/billing/ledger-payments/{payment.pk}/reverse/'

    def create_posted_rent_charge(self, amount_cents=10_000):
        self.client.force_authenticate(self.accountant)
        invoice_response = self.client.post(
            '/api/v1/billing/invoices/',
            self.invoice_payload(include_rent=False),
            format='json',
        )
        self.assertEqual(invoice_response.status_code, status.HTTP_201_CREATED)
        charge_response = self.client.post('/api/v1/billing/charges/', {
            'invoice': invoice_response.data['id'],
            'charge_type': 'RENT',
            'amount_cents': amount_cents,
            'due_date': '2026-10-05',
        }, format='json')
        self.assertEqual(charge_response.status_code, status.HTTP_201_CREATED)
        post_response = self.client.post(f"/api/v1/billing/invoices/{invoice_response.data['id']}/post/")
        self.assertEqual(post_response.status_code, status.HTTP_200_OK)
        return (
            Invoice.objects.get(pk=invoice_response.data['id']),
            Charge.objects.get(pk=charge_response.data['id']),
        )

    def test_manual_receipt_settles_canonical_ledger_and_statement(self):
        invoice, charge = self.create_posted_rent_charge(10_000)

        response = self.client.post('/api/v1/billing/ledger-payments/manual-receipts/', {
            'tenant': self.tenant.pk,
            'amount_cents': 4_000,
            'received_date': '2026-10-06',
            'method': 'CASH',
            'reference': 'CASH-RECEIPT-001',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment = Payment.objects.get(pk=response.data['id'])
        charge.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(payment.status, Payment.Status.ALLOCATED)
        self.assertEqual(payment.recorded_by_id, self.accountant.pk)
        self.assertEqual(payment.method, Payment.Method.CASH)
        self.assertEqual(payment.reference, 'CASH-RECEIPT-001')
        self.assertEqual(payment.allocated_cents, 4_000)
        self.assertEqual(payment.overpayment_cents, 0)
        self.assertEqual(charge.balance_cents, 6_000)
        self.assertEqual(invoice.balance_cents, 6_000)
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 1)
        debits = sum(row.amount_cents for row in LedgerPosting.objects.filter(payment=payment, direction='DEBIT'))
        credits = sum(row.amount_cents for row in LedgerPosting.objects.filter(payment=payment, direction='CREDIT'))
        self.assertEqual((debits, credits), (4_000, 4_000))
        self.assertTrue(AuditLog.objects.filter(action='payment.manual_receipt', object_id=str(payment.pk)).exists())

        self.client.force_authenticate(self.tenant_user)
        payment_history = self.client.get('/api/v1/billing/ledger-payments/')
        self.assertEqual(payment_history.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in payment_history.data], [str(payment.pk)])
        statement = self.client.get('/api/v1/billing/statements/me/', {
            'from': '2026-10-01', 'to': '2026-10-31',
        })
        self.assertEqual(statement.status_code, status.HTTP_200_OK)
        self.assertTrue(any(
            line['kind'] == 'payment' and line['credit_cents'] == 4_000
            for line in statement.data['lines']
        ))
        delinquency = self.client.get('/api/v1/billing/delinquency/', {
            'tenant': self.tenant.pk, 'as_of': '2026-10-10', 'grace_days': 0,
        })
        self.assertEqual(delinquency.status_code, status.HTTP_200_OK)
        self.assertEqual(delinquency.data['delinquent_cents'], 6_000)

    def test_manual_receipt_overpayment_is_canonical_tenant_credit(self):
        invoice, charge = self.create_posted_rent_charge(10_000)

        response = self.client.post('/api/v1/billing/ledger-payments/manual-receipts/', {
            'tenant': self.tenant.pk,
            'amount_cents': 12_500,
            'received_date': '2026-10-06',
            'method': 'BANK_TRANSFER',
            'reference': 'BANK-RECEIPT-OVERPAY',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment = Payment.objects.get(pk=response.data['id'])
        charge.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual((payment.allocated_cents, payment.overpayment_cents), (10_000, 2_500))
        self.assertEqual((charge.balance_cents, invoice.balance_cents), (0, 0))
        self.assertTrue(LedgerPosting.objects.filter(
            payment=payment, account='2020', direction='CREDIT', amount_cents=2_500,
        ).exists())

    def test_manual_receipt_retry_is_idempotent_and_rolls_back_on_failure(self):
        _invoice, charge = self.create_posted_rent_charge(10_000)
        payload = {
            'tenant': self.tenant.pk,
            'amount_cents': 4_000,
            'received_date': '2026-10-06',
            'method': 'CASH',
            'reference': 'CASH-RECEIPT-IDEMPOTENT',
        }
        first = self.client.post('/api/v1/billing/ledger-payments/manual-receipts/', payload, format='json')
        second = self.client.post('/api/v1/billing/ledger-payments/manual-receipts/', payload, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['id'], second.data['id'])
        payment = Payment.objects.get(pk=first.data['id'])
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 1)
        self.assertEqual(LedgerPosting.objects.filter(payment=payment).count(), 2)

        failing_payload = {**payload, 'reference': 'CASH-RECEIPT-ROLLBACK'}
        with patch('application.services.billing.allocate_payment', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                self.client.post('/api/v1/billing/ledger-payments/manual-receipts/', failing_payload, format='json')
        charge.refresh_from_db()
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(charge.balance_cents, 6_000)

    def test_manual_receipt_reference_collision_with_history_requires_reconciliation(self):
        _invoice, charge = self.create_posted_rent_charge(10_000)
        legacy = RentPayment.objects.create(
            lease=self.lease,
            recorded_by=self.accountant,
            due_date=date(2026, 10, 5),
            amount_minor=4_000,
            status=RentPayment.Status.PAID,
            paid_at=timezone.now(),
            method='CASH',
            reference='LEGACY-RECEIPT-001',
        )
        original = (legacy.amount_minor, legacy.status, legacy.reference, legacy.lease_id)

        response = self.client.post('/api/v1/billing/ledger-payments/manual-receipts/', {
            'tenant': self.tenant.pk,
            'amount_cents': 4_000,
            'received_date': '2026-10-06',
            'method': 'CASH',
            'reference': 'LEGACY-RECEIPT-001',
        }, format='json')

        self.assertEqual(response.status_code, 409)
        self.assertIn('reference', response.data)
        self.assertIn('Reconciliation is required', str(response.data['reference']))
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(PaymentAllocation.objects.exists())
        self.assertFalse(LedgerPosting.objects.exists())
        charge.refresh_from_db()
        legacy.refresh_from_db()
        self.assertEqual(charge.balance_cents, 10_000)
        self.assertEqual((legacy.amount_minor, legacy.status, legacy.reference, legacy.lease_id), original)

    def test_manual_receipt_reference_collision_is_scoped_to_organization(self):
        self.create_posted_rent_charge(10_000)
        other_tenant = Tenant.objects.create(
            organization=self.other,
            first_name='Brian',
            last_name='Mwangi',
            phone_number='+254711111111',
        )
        other_property = Property.objects.create(organization=self.other, name='Other Acacia')
        other_building = Building.objects.create(property=other_property, name='Block B')
        other_unit = Unit.objects.create(building=other_building, name='B-1')
        other_lease = Lease.objects.create(
            tenant=other_tenant,
            unit=other_unit,
            reference='OTHER-LEASE-1',
            start_date=date(2026, 10, 1),
            monthly_rent_minor=100_000,
        )
        RentPayment.objects.create(
            lease=other_lease,
            recorded_by=self.outsider,
            due_date=date(2026, 10, 5),
            amount_minor=4_000,
            status=RentPayment.Status.PAID,
            reference='ORG-SCOPED-RECEIPT',
        )

        self.client.force_authenticate(self.accountant)
        response = self.client.post('/api/v1/billing/ledger-payments/manual-receipts/', {
            'tenant': self.tenant.pk,
            'amount_cents': 4_000,
            'received_date': '2026-10-06',
            'method': 'CASH',
            'reference': 'ORG-SCOPED-RECEIPT',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Payment.objects.get(pk=response.data['id']).organization_id, self.organization.pk)

    def test_historical_row_added_after_reconciliation_does_not_duplicate_canonical_payment(self):
        self.create_posted_rent_charge(10_000)
        payload = {
            'tenant': self.tenant.pk,
            'amount_cents': 4_000,
            'received_date': '2026-10-06',
            'method': 'CASH',
            'reference': 'RECONCILED-LEGACY-REF',
        }
        first = self.client.post('/api/v1/billing/ledger-payments/manual-receipts/', payload, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        legacy = RentPayment.objects.create(
            lease=self.lease,
            recorded_by=self.accountant,
            due_date=date(2026, 10, 5),
            amount_minor=4_000,
            status=RentPayment.Status.PAID,
            reference=payload['reference'],
        )

        retry = self.client.post('/api/v1/billing/ledger-payments/manual-receipts/', payload, format='json')

        self.assertEqual(retry.status_code, status.HTTP_200_OK, retry.data)
        self.assertEqual(retry.data['id'], first.data['id'])
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(PaymentAllocation.objects.filter(payment_id=first.data['id']).count(), 1)
        legacy.refresh_from_db()
        self.assertEqual(legacy.status, RentPayment.Status.PAID)

    def test_manual_receipt_requires_authorized_staff_and_disallows_mpesa(self):
        self.create_posted_rent_charge(10_000)
        payload = {
            'tenant': self.tenant.pk,
            'amount_cents': 1_000,
            'received_date': '2026-10-06',
            'method': 'CASH',
            'reference': 'CASH-RECEIPT-AUTH',
        }
        self.client.force_authenticate(self.tenant_user)
        tenant_response = self.client.post('/api/v1/billing/ledger-payments/manual-receipts/', payload, format='json')
        self.client.force_authenticate(self.outsider)
        outsider_response = self.client.post('/api/v1/billing/ledger-payments/manual-receipts/', payload, format='json')
        self.client.force_authenticate(self.accountant)
        unverified_mpesa = self.client.post('/api/v1/billing/ledger-payments/', {
            **payload, 'method': 'MPESA', 'reference': 'MPESA-MANUAL-BLOCKED',
        }, format='json')
        self.assertEqual(tenant_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(outsider_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(unverified_mpesa.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Payment.objects.count(), 0)

    def test_payment_amount_database_limit_is_validated_before_persistence(self):
        self.client.force_authenticate(self.accountant)
        accepted = self.client.post('/api/v1/billing/ledger-payments/', {
            'tenant': self.tenant.pk,
            'amount_cents': MAX_MONEY_CENTS,
            'received_date': '2026-10-06',
            'method': 'CASH',
            'reference': 'MAX-RANGE-PAYMENT',
        }, format='json')
        rejected = self.client.post('/api/v1/billing/ledger-payments/', {
            'tenant': self.tenant.pk,
            'amount_cents': MAX_MONEY_CENTS + 1,
            'received_date': '2026-10-06',
            'method': 'CASH',
            'reference': 'OVER-RANGE-PAYMENT',
        }, format='json')
        self.assertEqual(accepted.status_code, status.HTTP_201_CREATED)
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('amount_cents', rejected.data)

    def test_canonical_payment_service_rejects_amount_above_storage_range(self):
        with self.assertRaises(ValidationError):
            record_payment(
                tenant=self.tenant,
                amount_cents=MAX_MONEY_CENTS + 1,
                received_date=date(2026, 10, 6),
                method=Payment.Method.CASH,
                actor=self.accountant,
            )
        self.assertFalse(Payment.objects.exists())

    def test_canonical_payment_service_rejects_unverified_mpesa(self):
        with self.assertRaises(ValidationError) as caught:
            record_payment(
                tenant=self.tenant,
                amount_cents=2_000,
                received_date=date(2026, 10, 6),
                method=Payment.Method.MPESA,
                actor=self.accountant,
                reference='TEST-UNVERIFIED-MPESA',
                external_id='TEST-UNVERIFIED-MPESA',
            )

        self.assertIn('method', caught.exception.detail)
        self.assertFalse(Payment.objects.exists())

    def test_invoice_aggregate_cannot_overflow_database_money_range(self):
        self.client.force_authenticate(self.accountant)
        invoice_response = self.client.post(
            '/api/v1/billing/invoices/', self.invoice_payload(include_rent=False), format='json',
        )
        self.assertEqual(invoice_response.status_code, status.HTTP_201_CREATED)
        invoice_id = invoice_response.data['id']
        first = self.client.post('/api/v1/billing/charges/', {
            'invoice': invoice_id, 'charge_type': 'RENT', 'amount_cents': MAX_MONEY_CENTS,
            'due_date': '2026-10-05',
        }, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        overflow = self.client.post('/api/v1/billing/charges/', {
            'invoice': invoice_id, 'charge_type': 'RENT', 'amount_cents': 1,
            'due_date': '2026-10-05',
        }, format='json')
        self.assertEqual(overflow.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('amount_cents', overflow.data)
        self.assertEqual(Charge.objects.filter(invoice_id=invoice_id).count(), 1)
        self.assertEqual(Invoice.objects.get(pk=invoice_id).total_cents, MAX_MONEY_CENTS)

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
            'method': 'BANK_TRANSFER',
            'reference': 'BANK-1',
            'external_id': 'bank-txn-1',
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

    def test_current_rent_generation_uses_start_rate_and_ignores_schedule_frequency(self):
        # Characterizes the existing behavior pending an approved rental
        # billing policy: schedule frequency is stored but not interpreted,
        # and a mid-period rate change does not split the generated charge.
        RentSchedule.objects.create(
            lease=self.lease,
            effective_from=date(2026, 10, 1),
            effective_to=date(2026, 10, 15),
            amount_minor=70_000,
            frequency=RentSchedule.Frequency.WEEKLY,
        )
        RentSchedule.objects.create(
            lease=self.lease,
            effective_from=date(2026, 10, 15),
            amount_minor=210_000,
            frequency=RentSchedule.Frequency.QUARTERLY,
        )

        actual = rent_charge_amount(self.lease, date(2026, 10, 1), date(2026, 10, 31))

        self.assertEqual(actual, prorate_move_in(70_000, date(2026, 10, 15)).charge_cents)

    def test_current_rent_generation_does_not_prorate_a_mid_period_move_out(self):
        # Characterizes the existing full-rate result without choosing the
        # disputed future move-out proration rule.
        self.lease.start_date = date(2026, 10, 1)
        self.lease.end_date = date(2026, 10, 15)
        self.lease.save(update_fields=('start_date', 'end_date'))

        actual = rent_charge_amount(self.lease, date(2026, 10, 1), date(2026, 10, 31))

        self.assertEqual(actual, self.lease.monthly_rent_minor)

    def test_posted_rent_charge_creates_balanced_journal(self):
        invoice, charge = self.create_posted_rent_charge(10_000)

        entries = list(
            ChargeJournalEntry.objects.filter(
                charge=charge,
                reverses__isnull=True,
            ).order_by("direction")
        )

        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {(entry.account, entry.direction, entry.amount_cents) for entry in entries},
            {
                ("1100", "DEBIT", 10_000),
                ("4010", "CREDIT", 10_000),
            },
        )
        self.assertEqual(
            sum(e.amount_cents for e in entries if e.direction == "DEBIT"),
            sum(e.amount_cents for e in entries if e.direction == "CREDIT"),
        )
        self.assertEqual(charge.lifecycle, DocumentStatus.POSTED)

    def test_posted_other_charge_uses_other_tenant_charges_account(self):
        self.client.force_authenticate(self.accountant)
        created = self.client.post(
            "/api/v1/billing/invoices/",
            self.invoice_payload(include_rent=False),
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        charge_response = self.client.post("/api/v1/billing/charges/", {
            "invoice": created.data["id"],
            "charge_type": "WATER",
            "amount_cents": 2_500,
            "due_date": "2026-10-05",
        }, format="json")
        self.assertEqual(charge_response.status_code, status.HTTP_201_CREATED)

        posted = self.client.post(
            f"/api/v1/billing/invoices/{created.data['id']}/post/"
        )
        self.assertEqual(posted.status_code, status.HTTP_200_OK)

        charge = Charge.objects.get(pk=charge_response.data["id"])
        entries = list(ChargeJournalEntry.objects.filter(charge=charge))

        self.assertEqual(
            {(entry.account, entry.direction, entry.amount_cents) for entry in entries},
            {
                ("1100", "DEBIT", 2_500),
                ("4020", "CREDIT", 2_500),
            },
        )

    def test_void_posted_invoice_reverses_journal_without_deleting_originals(self):
        invoice, charge = self.create_posted_rent_charge(10_000)
        originals = list(
            ChargeJournalEntry.objects.filter(
                charge=charge,
                reverses__isnull=True,
            )
        )
        self.assertEqual(len(originals), 2)

        response = self.client.post(
            f"/api/v1/billing/invoices/{invoice.pk}/void/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        all_entries = list(
            ChargeJournalEntry.objects.filter(charge=charge).order_by("pk")
        )
        self.assertEqual(len(all_entries), 4)
        self.assertEqual(
            ChargeJournalEntry.objects.filter(
                charge=charge,
                reverses__isnull=True,
            ).count(),
            2,
        )

        reversals = [entry for entry in all_entries if entry.reverses_id]
        self.assertEqual(len(reversals), 2)
        for reversal in reversals:
            original = next(
                entry for entry in originals if entry.pk == reversal.reverses_id
            )
            self.assertEqual(reversal.account, original.account)
            self.assertEqual(reversal.amount_cents, original.amount_cents)
            self.assertNotEqual(reversal.direction, original.direction)

        self.assertEqual(
            sum(e.amount_cents for e in all_entries if e.direction == "DEBIT"),
            sum(e.amount_cents for e in all_entries if e.direction == "CREDIT"),
        )

    def test_void_accepts_correct_existing_journal_reversals_without_duplicates(self):
        invoice, charge = self.create_posted_rent_charge(10_000)
        originals = list(
            ChargeJournalEntry.objects.filter(
                charge=charge, reverses__isnull=True,
            ).order_by("pk")
        )

        for original in originals:
            ChargeJournalEntry.objects.create(
                charge=charge,
                account=original.account,
                direction=(
                    ChargeJournalEntry.Direction.CREDIT
                    if original.direction == ChargeJournalEntry.Direction.DEBIT
                    else ChargeJournalEntry.Direction.DEBIT
                ),
                amount_cents=original.amount_cents,
                reverses=original,
            )

        response = self.client.post(
            f"/api/v1/billing/invoices/{invoice.pk}/void/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            ChargeJournalEntry.objects.filter(charge=charge).count(), 4,
        )
        self.assertEqual(
            ChargeJournalEntry.objects.filter(
                charge=charge, reverses__isnull=False,
            ).count(), 2,
        )

    def test_void_rejects_existing_reversal_with_wrong_amount(self):
        invoice, charge = self.create_posted_rent_charge(10_000)
        original = ChargeJournalEntry.objects.get(
            charge=charge, reverses__isnull=True, direction="DEBIT",
        )
        ChargeJournalEntry.objects.create(
            charge=charge,
            account=original.account,
            direction=ChargeJournalEntry.Direction.CREDIT,
            amount_cents=original.amount_cents + 1,
            reverses=original,
        )

        response = self.client.post(
            f"/api/v1/billing/invoices/{invoice.pk}/void/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        invoice.refresh_from_db()
        charge.refresh_from_db()
        self.assertEqual(invoice.status, DocumentStatus.POSTED)
        self.assertEqual(charge.lifecycle, DocumentStatus.POSTED)
        self.assertEqual(
            ChargeJournalEntry.objects.filter(
                charge=charge, reverses__isnull=False,
            ).count(), 1,
        )

    def test_void_rejects_existing_reversal_with_wrong_direction(self):
        invoice, charge = self.create_posted_rent_charge(10_000)
        original = ChargeJournalEntry.objects.get(
            charge=charge, reverses__isnull=True, direction="DEBIT",
        )
        ChargeJournalEntry.objects.create(
            charge=charge,
            account=original.account,
            direction=original.direction,
            amount_cents=original.amount_cents,
            reverses=original,
        )

        response = self.client.post(
            f"/api/v1/billing/invoices/{invoice.pk}/void/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, DocumentStatus.POSTED)

    def test_void_rejects_incomplete_original_journal(self):
        invoice, charge = self.create_posted_rent_charge(10_000)
        original = ChargeJournalEntry.objects.filter(
            charge=charge, reverses__isnull=True,
        ).order_by("pk").first()

        # QuerySet.delete() deliberately simulates damaged legacy/database
        # data; the normal model API prevents deleting journal entries.
        ChargeJournalEntry.objects.filter(pk=original.pk).delete()

        response = self.client.post(
            f"/api/v1/billing/invoices/{invoice.pk}/void/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        invoice.refresh_from_db()
        charge.refresh_from_db()
        self.assertEqual(invoice.status, DocumentStatus.POSTED)
        self.assertEqual(charge.lifecycle, DocumentStatus.POSTED)
        self.assertEqual(
            ChargeJournalEntry.objects.filter(
                charge=charge, reverses__isnull=True,
            ).count(), 1,
        )
        self.assertFalse(
            ChargeJournalEntry.objects.filter(
                charge=charge, reverses__isnull=False,
            ).exists()
        )

    @patch("application.services.billing._create_charge_journal")
    def test_posting_rolls_back_all_changes_when_journal_creation_fails(
        self, create_journal,
    ):
        self.client.force_authenticate(self.accountant)

        created = self.client.post(
            "/api/v1/billing/invoices/",
            self.invoice_payload(include_rent=False),
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        charge_ids = []
        for charge_type, amount in (("RENT", 10_000), ("WATER", 2_500)):
            response = self.client.post("/api/v1/billing/charges/", {
                "invoice": created.data["id"],
                "charge_type": charge_type,
                "amount_cents": amount,
                "due_date": "2026-10-05",
            }, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            charge_ids.append(response.data["id"])

        def fail_on_second_charge(charge):
            if str(charge.pk) == str(charge_ids[1]):
                raise RuntimeError("Simulated journal failure")
            return []

        create_journal.side_effect = fail_on_second_charge

        from application.services.billing import post_invoice

        invoice = Invoice.objects.get(pk=created.data["id"])
        with self.assertRaises(RuntimeError):
            post_invoice(invoice, actor=self.accountant)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, DocumentStatus.DRAFT)
        self.assertTrue(
            Charge.objects.filter(
                pk__in=charge_ids,
                lifecycle=DocumentStatus.DRAFT,
            ).count() == 2
        )
        self.assertEqual(
            ChargeJournalEntry.objects.filter(charge_id__in=charge_ids).count(),
            0,
        )

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

    def test_deactivated_tenant_cannot_read_own_delinquency(self):
        self.tenant.is_active = False
        self.tenant.save(update_fields=('is_active', 'updated_at'))
        self.client.force_authenticate(self.tenant_user)
        response = self.client.get('/api/v1/billing/delinquency/', {
            'tenant': self.tenant.pk,
            'as_of': '2026-10-10',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_deactivated_tenant_organization_records_are_hidden_with_other_org_access(self):
        invoice = Invoice.objects.create(
            organization=self.organization,
            tenant=self.tenant,
            lease=self.lease,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            due_date=date(2026, 10, 5),
            status=DocumentStatus.POSTED,
            total_cents=1000,
            balance_cents=1000,
        )
        charge = Charge.objects.create(
            invoice=invoice,
            organization=self.organization,
            tenant=self.tenant,
            charge_type='RENT',
            amount_cents=1000,
            balance_cents=1000,
            due_date=date(2026, 10, 5),
            lifecycle=DocumentStatus.POSTED,
        )
        Payment.objects.create(
            organization=self.organization,
            tenant=self.tenant,
            amount_cents=1000,
            received_date=date(2026, 10, 5),
            execution_timestamp=timezone.now(),
            method=Payment.Method.CASH,
            recorded_by=self.owner,
        )
        OrganizationMembership.objects.create(
            organization=self.other,
            user=self.tenant_user,
            role=OrganizationMembership.Role.OWNER,
        )
        self.organization.is_active = False
        self.organization.save(update_fields=('is_active', 'updated_at'))
        self.client.force_authenticate(self.tenant_user)

        invoice_response = self.client.get('/api/v1/billing/invoices/')
        charge_response = self.client.get('/api/v1/billing/charges/')
        payment_response = self.client.get('/api/v1/billing/ledger-payments/')

        self.assertEqual(invoice_response.status_code, status.HTTP_200_OK)
        self.assertEqual(charge_response.status_code, status.HTTP_200_OK)
        self.assertEqual(payment_response.status_code, status.HTTP_200_OK)
        self.assertEqual(invoice_response.data, [])
        self.assertEqual(charge_response.data, [])
        self.assertEqual(payment_response.data, [])

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
        worker_pids = []

        def reverse_in_own_connection():
            from application.services.billing import reverse_payment

            try:
                close_old_connections()
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    worker_pids.append(cursor.fetchone()[0])
                user = get_user_model().objects.get(pk=actor_id)
                target = Payment.objects.get(pk=payment_id)
                return reverse_payment(target, reason='Concurrent duplicate', actor=user).pk
            finally:
                # CONN_MAX_AGE keeps healthy connections open; close this
                # thread-local connection before the worker exits so Django
                # can drop the temporary test database during teardown.
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: reverse_in_own_connection(), range(2)))
        self.assertEqual(results[0], results[1])
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT count(*) FROM pg_stat_activity WHERE pid = ANY(%s)',
                [worker_pids],
            )
            self.assertEqual(cursor.fetchone()[0], 0)
        payment.refresh_from_db()
        self.assertEqual(PaymentReversal.objects.filter(payment=payment).count(), 1)
        self.assertEqual(LedgerPosting.objects.filter(payment=payment).count(), 4)

    def test_concurrent_reversals_preserve_shared_invoice_balance(self):
        actor = get_user_model().objects.create_user(username='shared-invoice-reversal', password='test')
        organization = Organization.objects.create(name='Shared Invoice Concurrency Homes')
        tenant = Tenant.objects.create(
            organization=organization,
            first_name='Concurrent',
            last_name='Tenant',
            phone_number='+254700000090',
        )
        invoice = Invoice.objects.create(
            organization=organization,
            tenant=tenant,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            due_date=date(2026, 10, 5),
            status=DocumentStatus.POSTED,
            total_cents=6_000,
            balance_cents=0,
        )
        payments = []
        for index in range(2):
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
            payments.append(payment.pk)

        barrier = Barrier(2, timeout=10)
        actor_id = actor.pk

        def reverse_in_own_connection(payment_id):
            from application.services.billing import reverse_payment

            try:
                close_old_connections()
                user = get_user_model().objects.get(pk=actor_id)
                target = Payment.objects.get(pk=payment_id)
                barrier.wait(timeout=10)
                return reverse_payment(target, reason='Concurrent shared invoice reversal', actor=user).pk
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            reversal_ids = list(pool.map(reverse_in_own_connection, payments))

        self.assertEqual(len(set(reversal_ids)), 2)
        invoice.refresh_from_db()
        self.assertEqual(invoice.balance_cents, 6_000)
        self.assertEqual(PaymentReversal.objects.filter(pk__in=reversal_ids).count(), 2)


@skipUnless(connection.vendor == 'postgresql', 'Concurrent receipt test requires PostgreSQL.')
class ManualReceiptConcurrencyTests(TransactionTestCase):
    def test_two_identical_concurrent_receipts_create_one_payment_and_allocation(self):
        user_model = get_user_model()
        actor = user_model.objects.create_user(username='manual-receipt-concurrency', password='test')
        organization = Organization.objects.create(name='Manual Receipt Concurrency Homes')
        OrganizationMembership.objects.create(
            organization=organization, user=actor, role=OrganizationMembership.Role.ACCOUNTANT,
        )
        tenant = Tenant.objects.create(
            organization=organization,
            first_name='Concurrent',
            last_name='Receipt',
            phone_number='+254700000091',
        )
        invoice = Invoice.objects.create(
            organization=organization, tenant=tenant,
            period_start=date(2026, 10, 1), period_end=date(2026, 10, 31),
            due_date=date(2026, 10, 5), status=DocumentStatus.POSTED,
            total_cents=5_000, balance_cents=5_000,
        )
        charge = Charge.objects.create(
            invoice=invoice, organization=organization, tenant=tenant,
            charge_type='RENT', amount_cents=5_000, balance_cents=5_000,
            due_date=date(2026, 10, 5), lifecycle=DocumentStatus.POSTED,
        )
        actor_id, tenant_id = actor.pk, tenant.pk
        barrier = Barrier(2)
        worker_pids = []

        def submit_in_own_connection():
            try:
                close_old_connections()
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    worker_pids.append(cursor.fetchone()[0])
                actor_row = user_model.objects.get(pk=actor_id)
                tenant_row = Tenant.objects.get(pk=tenant_id)
                barrier.wait(timeout=10)
                payment, duplicate = record_manual_receipt(
                    tenant=tenant_row, amount_cents=3_000,
                    received_date=date(2026, 10, 6), method=Payment.Method.CASH,
                    reference='CONCURRENT-RECEIPT-001', actor=actor_row,
                )
                return str(payment.pk), duplicate
            finally:
                # close_old_connections() intentionally preserves a healthy
                # connection when CONN_MAX_AGE is nonzero.
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: submit_in_own_connection(), range(2)))

        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(duplicate for _payment_id, duplicate in results), [False, True])
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT count(*) FROM pg_stat_activity WHERE pid = ANY(%s)',
                [worker_pids],
            )
            self.assertEqual(cursor.fetchone()[0], 0)
        self.assertEqual(Payment.objects.count(), 1)
        payment = Payment.objects.get()
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 1)
        self.assertEqual(LedgerPosting.objects.filter(payment=payment).count(), 2)
        charge.refresh_from_db()
        self.assertEqual(charge.balance_cents, 2_000)
