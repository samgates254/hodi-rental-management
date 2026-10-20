from datetime import date
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.billing.models import (
    Charge,
    ChargeJournalEntry,
    DocumentStatus,
    Invoice,
)
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant
from django.contrib.auth import get_user_model


class JournalPostedChargesCommandTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="journal-command-owner",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Journal Command Test Homes",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
        )
        self.tenant_user = user_model.objects.create_user(
            username="journal-command-tenant",
            password="test-password",
        )
        self.tenant = Tenant.objects.create(
            organization=self.organization,
            user=self.tenant_user,
            first_name="Test",
            last_name="Tenant",
            phone_number="+254700000099",
        )
        property_record = Property.objects.create(
            organization=self.organization,
            name="Journal Test Property",
        )
        building = Building.objects.create(
            property=property_record,
            name="Block A",
        )
        self.unit = Unit.objects.create(
            building=building,
            name="A-1",
        )

        self.invoice = Invoice.objects.create(
            organization=self.organization,
            tenant=self.tenant,
            lease=None,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            due_date=date(2026, 10, 5),
            status=DocumentStatus.POSTED,
        )
        self.charge = Charge.objects.create(
            invoice=self.invoice,
            organization=self.organization,
            tenant=self.tenant,
            charge_type="RENT",
            amount_cents=290323,
            balance_cents=290323,
            due_date=date(2026, 10, 5),
            lifecycle=DocumentStatus.POSTED,
            currency="KES",
        )

    def run_command(self, *args):
        output = StringIO()
        call_command("journal_posted_charges", *args, stdout=output)
        return output.getvalue()

    def test_dry_run_does_not_create_entries(self):
        output = self.run_command("--limit", "1000")

        self.assertIn("ELIGIBLE=1", output)
        self.assertIn("DRY RUN", output)
        self.assertEqual(
            ChargeJournalEntry.objects.filter(charge=self.charge).count(),
            0,
        )

    def test_apply_creates_two_balanced_entries(self):
        output = self.run_command("--apply")

        self.assertIn("CREATED=1", output)
        entries = list(
            ChargeJournalEntry.objects.filter(
                charge=self.charge,
                reverses__isnull=True,
            )
        )
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {(e.account, e.direction, e.amount_cents) for e in entries},
            {
                ("1100", "DEBIT", 290323),
                ("4010", "CREDIT", 290323),
            },
        )

    def test_repeated_apply_does_not_duplicate_entries(self):
        self.run_command("--apply")
        output = self.run_command("--apply")

        self.assertIn("ALREADY_OK=1", output)
        self.assertEqual(
            ChargeJournalEntry.objects.filter(
                charge=self.charge,
                reverses__isnull=True,
            ).count(),
            2,
        )

    def test_second_entry_failure_rolls_back_first_entry(self):
        original_create = ChargeJournalEntry.objects.create

        def fail_on_credit(*args, **kwargs):
            if kwargs.get("direction") == ChargeJournalEntry.Direction.CREDIT:
                raise RuntimeError("simulated database failure")
            return original_create(*args, **kwargs)

        output = StringIO()
        with patch(
            "apps.billing.management.commands.journal_posted_charges."
            "ChargeJournalEntry.objects.create",
            side_effect=fail_on_credit,
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "journal_posted_charges",
                    "--apply",
                    stdout=output,
                )

        self.assertIn("ERROR=1", output.getvalue())
        self.assertEqual(
            ChargeJournalEntry.objects.filter(charge=self.charge).count(),
            0,
        )
