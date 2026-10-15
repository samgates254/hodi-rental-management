from datetime import date
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import (
    Charge,
    ChargeJournalEntry,
    DocumentStatus,
    Invoice,
)
from apps.organizations.models import Organization, OrganizationMembership
from apps.tenants.models import Tenant


class ChargeJournalReportTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username='report-owner',
            password='test-password',
        )
        self.outsider = user_model.objects.create_user(
            username='report-outsider',
            password='test-password',
        )

        self.organization = Organization.objects.create(
            name='Reporting Homes',
        )
        self.other_organization = Organization.objects.create(
            name='Other Reporting Homes',
        )

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.outsider,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )

        self.tenant = Tenant.objects.create(
            organization=self.organization,
            first_name='Test',
            last_name='Tenant',
            phone_number='+254700000111',
        )

        self.invoice = Invoice.objects.create(
            organization=self.organization,
            tenant=self.tenant,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            due_date=date(2026, 10, 5),
            status=DocumentStatus.POSTED,
            currency='KES',
            total_cents=290323,
            balance_cents=290323,
        )

        self.charge = Charge.objects.create(
            invoice=self.invoice,
            organization=self.organization,
            tenant=self.tenant,
            charge_type='RENT',
            amount_cents=290323,
            balance_cents=290323,
            due_date=date(2026, 10, 5),
            lifecycle=DocumentStatus.POSTED,
            currency='KES',
        )

    def report_url(self, organization_id=None):
        organization_id = organization_id or self.organization.pk
        return f'/api/v1/reporting/charge-journal/?organization={organization_id}'

    def create_entry(self, account, direction, amount=290323):
        return ChargeJournalEntry.objects.create(
            charge=self.charge,
            account=account,
            direction=direction,
            amount_cents=amount,
        )

    def create_balanced_journal(self):
        self.create_entry('1100', 'DEBIT')
        self.create_entry('4010', 'CREDIT')

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get(self.report_url())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_can_read_balanced_rent_journal(self):
        self.create_balanced_journal()
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.report_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['summary']['inspected'], 1)
        self.assertEqual(response.data['summary']['ok'], 1)
        self.assertEqual(response.data['results'][0]['status'], 'OK')

    def test_missing_journal_is_reported(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.report_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['summary']['missing'], 1)
        self.assertEqual(response.data['results'][0]['status'], 'MISSING')

    def test_incorrect_account_is_reported(self):
        self.create_entry('1100', 'DEBIT')
        self.create_entry('4020', 'CREDIT')
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.report_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['summary']['inconsistent'], 1)

    def test_incorrect_amount_is_reported(self):
        self.create_entry('1100', 'DEBIT')
        self.create_entry('4010', 'CREDIT', amount=100000)
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.report_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['summary']['inconsistent'], 1)

    def test_other_organization_is_forbidden(self):
        self.client.force_authenticate(self.outsider)

        response = self.client.get(self.report_url())

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_organization_filter_does_not_expose_other_organizations(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(
            self.report_url(self.other_organization.pk),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_report_rejects_missing_organization_parameter(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get('/api/v1/reporting/charge-journal/')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    def test_unknown_charge_type_is_reported_inconsistent(self):
        self.charge.charge_type = 'UNKNOWN_TYPE'
        self.charge.save(update_fields=['charge_type'])
        self.create_entry('1100', 'DEBIT')
        self.create_entry('4010', 'CREDIT')
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.report_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['summary']['inconsistent'], 1)

    def test_missing_credit_line_is_reported_inconsistent(self):
        self.create_entry('1100', 'DEBIT')
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.report_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['summary']['inconsistent'], 1)

    def test_invalid_reversal_is_reported_inconsistent(self):
        original = self.create_entry('1100', 'DEBIT')
        self.create_entry('4010', 'CREDIT')

        ChargeJournalEntry.objects.create(
            charge=self.charge,
            account='1100',
            direction='DEBIT',
            amount_cents=290323,
            reverses=original,
        )
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.report_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['summary']['inconsistent'], 1)

    def test_charge_invoice_organization_mismatch_is_reported(self):
        self.charge.invoice = Invoice.objects.create(
        organization=self.other_organization,
        tenant=self.tenant,
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 31),
        due_date=date(2026, 10, 5),
        status=DocumentStatus.POSTED,
        currency='KES',
        total_cents=290323,
        balance_cents=290323,
        )
        self.charge.save(update_fields=['invoice'])
        self.create_balanced_journal()
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.report_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['summary']['inconsistent'], 1)

    def test_get_report_does_not_modify_journal_entries(self):
        self.create_balanced_journal()
        self.client.force_authenticate(self.owner)

        before = list(
            ChargeJournalEntry.objects.filter(charge=self.charge)
            .order_by('pk')
            .values_list(
                'pk', 'account', 'direction', 'amount_cents', 'reverses_id'
            )
        )

        response = self.client.get(self.report_url())

        after = list(
            ChargeJournalEntry.objects.filter(charge=self.charge)
            .order_by('pk')
            .values_list(
                'pk', 'account', 'direction', 'amount_cents', 'reverses_id'
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(after, before)
