from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.billing.models import (
    CHARGE_TYPES,
    DEPOSIT_CHARGE_TYPES,
    Charge,
    ChargeJournalEntry,
    DocumentStatus,
    MAX_MONEY_CENTS,
)


def expected_accounts(charge_type):
    normalized = (charge_type or "").strip().upper()

    if normalized in DEPOSIT_CHARGE_TYPES:
        return "1100", "2100"
    if normalized in ("RENT", "BASE_RENT"):
        return "1100", "4010"
    if normalized in CHARGE_TYPES:
        return "1100", "4020"

    return None


def inspect_original_journal(charge, accounts):
    entries = list(
        ChargeJournalEntry.objects.filter(
            charge=charge,
            reverses__isnull=True,
        ).order_by("pk")
    )

    if not entries:
        return "MISSING"

    if accounts is None:
        return "UNKNOWN_TYPE"

    expected = {
        (accounts[0], "DEBIT", charge.amount_cents),
        (accounts[1], "CREDIT", charge.amount_cents),
    }
    actual = {
        (entry.account, entry.direction, entry.amount_cents)
        for entry in entries
    }

    if len(entries) != 2 or actual != expected:
        return "INCONSISTENT"

    return "OK"


class Command(BaseCommand):
    help = (
        "Backfill original journals for posted KES charges. "
        "Dry-run by default; pass --apply to write entries."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Create missing journal entries.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=1000,
            help="Maximum charges to inspect (1..10000).",
        )

    def handle(self, *args, **options):
        limit = options["limit"]

        if not 1 <= limit <= 10000:
            self.stderr.write(
                self.style.ERROR("--limit must be between 1 and 10000")
            )
            return

        apply_changes = options["apply"]

        charges = list(
            Charge.objects.filter(
                lifecycle=DocumentStatus.POSTED,
                currency="KES",
                invoice__status=DocumentStatus.POSTED,
            ).order_by("pk")[:limit]
        )

        counts = {
            "ELIGIBLE": 0,
            "CREATED": 0,
            "ALREADY_OK": 0,
            "INVALID_AMOUNT": 0,
            "UNKNOWN_TYPE": 0,
            "INCONSISTENT": 0,
            "ERROR": 0,
        }

        for snapshot in charges:
            accounts = expected_accounts(snapshot.charge_type)

            if (
                isinstance(snapshot.amount_cents, bool)
                or not isinstance(snapshot.amount_cents, int)
                or not 0 < snapshot.amount_cents <= MAX_MONEY_CENTS
            ):
                counts["INVALID_AMOUNT"] += 1
                self.stdout.write(f"{snapshot.pk}: INVALID_AMOUNT")
                continue

            if accounts is None:
                existing = ChargeJournalEntry.objects.filter(
                    charge=snapshot,
                    reverses__isnull=True,
                ).exists()
                state = "INCONSISTENT" if existing else "UNKNOWN_TYPE"
                counts[state] += 1
                self.stdout.write(f"{snapshot.pk}: {state}")
                continue

            if not apply_changes:
                state = inspect_original_journal(snapshot, accounts)
                if state == "MISSING":
                    counts["ELIGIBLE"] += 1
                elif state == "OK":
                    counts["ALREADY_OK"] += 1
                else:
                    counts[state] += 1

                self.stdout.write(f"{snapshot.pk}: {state}")
                continue

            try:
                with transaction.atomic():
                    charge = Charge.objects.select_for_update().get(
                        pk=snapshot.pk,
                        lifecycle=DocumentStatus.POSTED,
                        currency="KES",
                        invoice__status=DocumentStatus.POSTED,
                    )

                    if (
                        isinstance(charge.amount_cents, bool)
                        or not isinstance(charge.amount_cents, int)
                        or not 0 < charge.amount_cents <= MAX_MONEY_CENTS
                    ):
                        counts["INVALID_AMOUNT"] += 1
                        self.stdout.write(f"{charge.pk}: INVALID_AMOUNT")
                        continue

                    state = inspect_original_journal(charge, accounts)

                    if state == "OK":
                        counts["ALREADY_OK"] += 1
                    elif state == "MISSING":
                        debit_account, credit_account = accounts

                        ChargeJournalEntry.objects.create(
                            charge=charge,
                            account=debit_account,
                            direction=ChargeJournalEntry.Direction.DEBIT,
                            amount_cents=charge.amount_cents,
                        )
                        ChargeJournalEntry.objects.create(
                            charge=charge,
                            account=credit_account,
                            direction=ChargeJournalEntry.Direction.CREDIT,
                            amount_cents=charge.amount_cents,
                        )
                        counts["CREATED"] += 1
                        state = "CREATED"
                    else:
                        counts[state] += 1

                self.stdout.write(f"{charge.pk}: {state}")

            except Exception as exc:
                counts["ERROR"] += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"{snapshot.pk}: ERROR ({type(exc).__name__}); "
                        "transaction rolled back"
                    )
                )

        self.stdout.write(
            f"Inspected {len(charges)} charge(s). "
            + ", ".join(
                f"{key}={value}" for key, value in counts.items()
            )
        )

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN: no database writes made. "
                    "Pass --apply to create missing entries."
                )
            )
        elif counts["ERROR"]:
            raise CommandError(
                f"Backfill completed with {counts['ERROR']} error(s). "
                "Review the error output and reconcile affected charges."
            )
