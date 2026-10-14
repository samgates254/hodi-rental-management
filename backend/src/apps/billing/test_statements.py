from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.leases.models import Lease, RentSchedule
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant
from common.rental_dates import rental_business_date

from .models import Charge, DocumentStatus, Invoice, Payment


class TenantStatementTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.today = rental_business_date()
		self.owner = user_model.objects.create_user(username='stmt-owner', password='secret')
		self.tenant_user = user_model.objects.create_user(username='stmt-tenant', password='secret')
		self.other_user = user_model.objects.create_user(username='stmt-other', password='secret')
		self.organization = Organization.objects.create(name='Statement Homes')
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.owner,
			role=OrganizationMembership.Role.OWNER,
		)
		self.tenant = Tenant.objects.create(
			user=self.tenant_user,
			organization=self.organization,
			first_name='Ada',
			last_name='Tenant',
			phone_number='0700000000',
			email='ada@example.com',
			national_id='SECRET-ID-991',
		)
		property_record = Property.objects.create(
			organization=self.organization,
			name='Kilimani Court',
			city='Nairobi',
		)
		building = Building.objects.create(property=property_record, name='Block A')
		unit = Unit.objects.create(building=building, name='A-1')
		self.lease = Lease.objects.create(
			tenant=self.tenant,
			unit=unit,
			reference='LEASE-ADA',
			start_date=date(2026, 1, 1),
			monthly_rent_minor=6500000,
			status=Lease.Status.ACTIVE,
		)
		RentSchedule.objects.create(
			lease=self.lease,
			effective_from=date(2026, 1, 1),
			amount_minor=6500000,
		)
		self.invoice = Invoice.objects.create(
			organization=self.organization,
			tenant=self.tenant,
			lease=self.lease,
			period_start=self.today.replace(day=1),
			period_end=self.today,
			due_date=self.today,
			status=DocumentStatus.POSTED,
			total_cents=6500000,
			balance_cents=2500000,
		)
		Charge.objects.create(
			invoice=self.invoice,
			organization=self.organization,
			tenant=self.tenant,
			charge_type='RENT',
			description='October rent',
			amount_cents=6500000,
			balance_cents=2500000,
			due_date=self.today,
			lifecycle=DocumentStatus.POSTED,
		)
		Charge.objects.create(
			invoice=self.invoice,
			organization=self.organization,
			tenant=self.tenant,
			charge_type='WATER',
			description='Draft water',
			amount_cents=50000,
			balance_cents=50000,
			due_date=self.today,
			lifecycle=DocumentStatus.DRAFT,
		)
		overdue_day = self.today - timedelta(days=40)
		Charge.objects.create(
			invoice=self.invoice,
			organization=self.organization,
			tenant=self.tenant,
			charge_type='RENT',
			description='Older rent',
			amount_cents=100000,
			balance_cents=100000,
			due_date=overdue_day,
			lifecycle=DocumentStatus.POSTED,
		)
		Payment.objects.create(
			organization=self.organization,
			tenant=self.tenant,
			amount_cents=4000000,
			allocated_cents=4000000,
			overpayment_cents=15000,
			received_date=self.today,
			execution_timestamp=timezone.now(),
			method=Payment.Method.BANK_TRANSFER,
			status=Payment.Status.ALLOCATED,
			reference='RCPT-ADA',
			recorded_by=self.owner,
		)
		Payment.objects.create(
			organization=self.organization,
			tenant=self.tenant,
			amount_cents=90000,
			received_date=self.today,
			execution_timestamp=timezone.now(),
			method=Payment.Method.CASH,
			status=Payment.Status.VOIDED,
			reference='VOID-ADA',
			recorded_by=self.owner,
		)
		other_org = Organization.objects.create(name='Other Statement Homes')
		self.other = Tenant.objects.create(
			user=self.other_user,
			organization=other_org,
			first_name='Bena',
			last_name='Other',
			phone_number='0711111111',
			national_id='OTHER-SECRET',
		)
		other_property = Property.objects.create(organization=other_org, name='Other Court', city='Mombasa')
		other_building = Building.objects.create(property=other_property, name='Block B')
		other_unit = Unit.objects.create(building=other_building, name='B-9')
		other_lease = Lease.objects.create(
			tenant=self.other,
			unit=other_unit,
			reference='LEASE-BENA',
			start_date=date(2026, 1, 1),
			monthly_rent_minor=100,
			status=Lease.Status.ACTIVE,
		)
		other_invoice = Invoice.objects.create(
			organization=other_org,
			tenant=self.other,
			lease=other_lease,
			period_start=self.today.replace(day=1),
			period_end=self.today,
			due_date=self.today,
			status=DocumentStatus.POSTED,
			total_cents=8800000,
			balance_cents=8800000,
		)
		Charge.objects.create(
			invoice=other_invoice,
			organization=other_org,
			tenant=self.other,
			charge_type='RENT',
			description='Bena private rent',
			amount_cents=8800000,
			balance_cents=8800000,
			due_date=self.today,
			lifecycle=DocumentStatus.POSTED,
		)
		self.client = APIClient()

	def test_tenant_statement_uses_posted_ledger_only(self):
		self.client.force_authenticate(self.tenant_user)
		response = self.client.get('/api/v1/billing/statements/me/?period=current_month')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		data = response.data
		self.assertEqual(data['tenant']['name'], 'Ada Tenant')
		self.assertNotIn('national_id', data['tenant'])
		self.assertNotIn('SECRET-ID-991', str(data))
		self.assertNotIn('Bena', str(data))
		self.assertEqual(data['property']['name'], 'Kilimani Court')
		self.assertEqual(data['unit']['name'], 'A-1')
		self.assertEqual(data['lease']['reference'], 'LEASE-ADA')
		self.assertEqual(data['lease']['monthly_rent_minor'], 6500000)
		self.assertEqual(data['period_charges_cents'], 6500000)
		self.assertEqual(data['period_payments_cents'], 4000000)
		self.assertEqual(data['outstanding_cents'], 2600000)
		self.assertEqual(data['overdue_cents'], 100000)
		self.assertEqual(data['credit_cents'], 15000)
		self.assertEqual(data['current_balance_cents'], 2585000)
		self.assertTrue(data['rent_schedule'])
		descriptions = [row['description'] for row in data['lines']]
		self.assertIn('October rent', descriptions)
		self.assertNotIn('Draft water', descriptions)
		self.assertNotIn('Bena private rent', descriptions)
		self.assertTrue(any('RCPT-ADA' in row['description'] for row in data['lines']))

	def test_client_tenant_id_is_ignored(self):
		self.client.force_authenticate(self.tenant_user)
		response = self.client.get(
			f'/api/v1/billing/statements/me/?tenant={self.other.pk}&tenant_id={self.other.pk}',
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['tenant']['name'], 'Ada Tenant')
		self.assertEqual(response.data['outstanding_cents'], 2600000)

	def test_overdue_statement_uses_nairobi_business_date_across_utc_midnight(self):
		Charge.objects.create(
			invoice=self.invoice,
			organization=self.organization,
			tenant=self.tenant,
			charge_type='RENT',
			description='Due on previous UTC date',
			amount_cents=2500,
			balance_cents=2500,
			due_date=date(2026, 10, 14),
			lifecycle=DocumentStatus.POSTED,
		)
		self.client.force_authenticate(self.tenant_user)

		with patch('apps.billing.statements.rental_business_date', return_value=date(2026, 10, 14)):
			before_nairobi_midnight = self.client.get('/api/v1/billing/statements/me/?period=current_month')
		with patch('apps.billing.statements.rental_business_date', return_value=date(2026, 10, 15)):
			after_nairobi_midnight = self.client.get('/api/v1/billing/statements/me/?period=current_month')

		self.assertEqual(before_nairobi_midnight.status_code, status.HTTP_200_OK)
		self.assertEqual(after_nairobi_midnight.status_code, status.HTTP_200_OK)
		expected_due_day_delta = sum(Charge.objects.filter(
			tenant=self.tenant,
			lifecycle=DocumentStatus.POSTED,
			due_date=date(2026, 10, 14),
		).values_list('balance_cents', flat=True))
		self.assertEqual(
			after_nairobi_midnight.data['overdue_cents'],
			before_nairobi_midnight.data['overdue_cents'] + expected_due_day_delta,
		)

	def test_other_tenant_cannot_be_addressed_and_owner_without_link_is_not_found(self):
		self.client.force_authenticate(self.other_user)
		own = self.client.get('/api/v1/billing/statements/me/')
		self.assertEqual(own.status_code, status.HTTP_200_OK)
		self.assertEqual(own.data['tenant']['name'], 'Bena Other')
		self.assertEqual(own.data['period_charges_cents'], 8800000)
		self.assertNotIn('Ada', str(own.data))

		self.client.force_authenticate(self.owner)
		denied = self.client.get(f'/api/v1/billing/statements/me/?tenant={self.tenant.pk}')
		self.assertEqual(denied.status_code, status.HTTP_404_NOT_FOUND)

	def test_anonymous_and_bad_token_are_denied(self):
		anonymous = self.client.get('/api/v1/billing/statements/me/')
		self.assertEqual(anonymous.status_code, status.HTTP_401_UNAUTHORIZED)
		self.client.credentials(HTTP_AUTHORIZATION='Token not-a-real-token')
		invalid = self.client.get('/api/v1/billing/statements/me/pdf/')
		self.assertEqual(invalid.status_code, status.HTTP_401_UNAUTHORIZED)

	def test_inactive_tenant_link_is_not_found(self):
		self.tenant.is_active = False
		self.tenant.save(update_fields=('is_active',))
		self.client.force_authenticate(self.tenant_user)
		response = self.client.get('/api/v1/billing/statements/me/')
		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

	def test_dates_are_validated(self):
		self.client.force_authenticate(self.tenant_user)
		bad = self.client.get('/api/v1/billing/statements/me/?from=yesterday&to=2026-10-01')
		self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
		order = self.client.get('/api/v1/billing/statements/me/?from=2026-10-10&to=2026-10-01')
		self.assertEqual(order.status_code, status.HTTP_400_BAD_REQUEST)
		half = self.client.get('/api/v1/billing/statements/me/?from=2026-10-01')
		self.assertEqual(half.status_code, status.HTTP_400_BAD_REQUEST)
		span = self.client.get('/api/v1/billing/statements/me/?from=2020-01-01&to=2026-10-01')
		self.assertEqual(span.status_code, status.HTTP_400_BAD_REQUEST)
		unknown = self.client.get('/api/v1/billing/statements/me/?period=forever')
		self.assertEqual(unknown.status_code, status.HTTP_400_BAD_REQUEST)

	def test_pdf_is_generated_from_the_same_rows(self):
		token = Token.objects.create(user=self.tenant_user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
		response = self.client.get('/api/v1/billing/statements/me/pdf/?period=current_month')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response['Content-Type'], 'application/pdf')
		self.assertIn('attachment;', response['Content-Disposition'])
		self.assertIn('hodi-statement-', response['Content-Disposition'])
		self.assertNotIn('/', response['Content-Disposition'].split('filename=')[-1].strip('"'))
		body = b''.join(response.streaming_content) if getattr(response, 'streaming_content', None) else response.content
		self.assertTrue(body.startswith(b'%PDF'))
		self.assertIn(b'Ada Tenant', body)
		self.assertIn(b'October rent', body)
		self.assertIn(b'RCPT-ADA', body)
		self.assertNotIn(b'SECRET-ID-991', body)
		self.assertNotIn(b'Bena', body)
		self.assertNotIn(b'Bena private rent', body)

	def test_real_token_round_trip_matches_force_auth_totals(self):
		token = Token.objects.create(user=self.tenant_user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
		response = self.client.get('/api/v1/billing/statements/me/?period=lease')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['period']['label'], 'lease')
		self.assertEqual(response.data['outstanding_cents'], 2600000)
		self.assertGreaterEqual(response.data['period_charges_cents'], 6500000)
