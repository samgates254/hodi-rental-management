from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.leases.models import Lease
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant

from .models import RentPayment


class RentPaymentApiTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.owner = user_model.objects.create_user(username='owner', password='secret')
		self.caretaker = user_model.objects.create_user(username='caretaker', password='secret')
		self.tenant_user = user_model.objects.create_user(username='tenant', password='secret')
		self.organization = Organization.objects.create(name='First Homes')
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.owner,
			role=OrganizationMembership.Role.ACCOUNTANT,
		)
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.caretaker,
			role=OrganizationMembership.Role.CARETAKER,
		)
		tenant = Tenant.objects.create(
			user=self.tenant_user,
			organization=self.organization,
			first_name='Ada',
			last_name='Tenant',
			phone_number='0700000000',
		)
		property_record = Property.objects.create(organization=self.organization, name='First property')
		building = Building.objects.create(property=property_record, name='Block A')
		unit = Unit.objects.create(building=building, name='A-1')
		self.lease = Lease.objects.create(
			tenant=tenant,
			unit=unit,
			reference='LEASE-A',
			start_date=date(2026, 1, 1),
			monthly_rent_minor=100000,
		)
		self.payment = RentPayment.objects.create(
			lease=self.lease,
			recorded_by=self.owner,
			due_date=date(2026, 10, 1),
			amount_minor=100000,
		)
		other_organization = Organization.objects.create(name='Second Homes')
		other_tenant = Tenant.objects.create(
			organization=other_organization,
			first_name='Other',
			last_name='Tenant',
			phone_number='0711111111',
		)
		other_property = Property.objects.create(organization=other_organization, name='Second property')
		other_building = Building.objects.create(property=other_property, name='Block B')
		other_unit = Unit.objects.create(building=other_building, name='B-1')
		other_lease = Lease.objects.create(
			tenant=other_tenant,
			unit=other_unit,
			reference='LEASE-B',
			start_date=date(2026, 1, 1),
			monthly_rent_minor=100000,
		)
		RentPayment.objects.create(
			lease=other_lease,
			recorded_by=self.owner,
			due_date=date(2026, 10, 1),
			amount_minor=100000,
		)
		self.client = APIClient()

	def payment_payload(self):
		return {
			'lease': self.lease.pk,
			'due_date': '2026-11-01',
			'amount_minor': 105000,
			'status': 'PAID',
			'paid_at': '2026-11-01T12:00:00Z',
			'method': 'BANK_TRANSFER',
			'reference': 'BANK-002',
		}

	def test_caretaker_can_read_but_cannot_write_payments(self):
		self.client.force_authenticate(self.caretaker)

		list_response = self.client.get('/api/v1/billing/payments/')
		create_response = self.client.post(
			'/api/v1/billing/payments/',
			self.payment_payload(),
			format='json',
		)
		update_response = self.client.patch(
			f'/api/v1/billing/payments/{self.payment.pk}/',
			{'status': 'PAID'},
			format='json',
		)

		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(list_response.data), 1)
		payment_data = list_response.data[0]
		self.assertEqual(payment_data['organization'], self.organization.pk)
		self.assertEqual(payment_data['tenant_name'], 'Ada Tenant')
		self.assertEqual(payment_data['unit_name'], 'A-1')
		self.assertEqual(payment_data['lease_reference'], 'LEASE-A')
		self.assertEqual(payment_data['amount_minor'], 100000)
		self.assertEqual(payment_data['status'], 'PENDING')
		self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)
		self.assertEqual(update_response.status_code, status.HTTP_403_FORBIDDEN)
		self.payment.refresh_from_db()
		self.assertEqual(self.payment.status, RentPayment.Status.PENDING)

	def test_tenant_can_read_only_their_own_rent_payments(self):
		self.client.force_authenticate(self.tenant_user)

		list_response = self.client.get('/api/v1/billing/payments/')
		create_response = self.client.post(
			'/api/v1/billing/payments/',
			self.payment_payload(),
			format='json',
		)

		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(list_response.data), 1)
		self.assertEqual(list_response.data[0]['id'], self.payment.pk)
		self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)

	def test_caretaker_can_filter_payments_by_selected_organization(self):
		other_organization = Organization.objects.get(name='Second Homes')
		OrganizationMembership.objects.create(
			organization=other_organization,
			user=self.caretaker,
			role=OrganizationMembership.Role.CARETAKER,
		)
		self.client.force_authenticate(self.caretaker)

		response = self.client.get(
			'/api/v1/billing/payments/',
			{'organization': other_organization.pk},
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data), 1)
		self.assertEqual(response.data[0]['tenant_name'], 'Other Tenant')

	def test_accountant_can_create_and_update_payment(self):
		self.client.force_authenticate(self.owner)

		create_response = self.client.post(
			'/api/v1/billing/payments/',
			self.payment_payload(),
			format='json',
		)
		self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
		payment = RentPayment.objects.get(reference='BANK-002')
		self.assertEqual(payment.recorded_by, self.owner)

		update_response = self.client.patch(
			f'/api/v1/billing/payments/{payment.pk}/',
			{'status': 'OVERDUE'},
			format='json',
		)
		self.assertEqual(update_response.status_code, status.HTTP_200_OK)
		payment.refresh_from_db()
		self.assertEqual(payment.status, RentPayment.Status.OVERDUE)
