from collections import defaultdict

from django.db.models import Prefetch
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import (
    CHARGE_TYPES,
    DEPOSIT_CHARGE_TYPES,
    Charge,
    ChargeJournalEntry,
    DocumentStatus,
)
from apps.organizations.models import OrganizationMembership


REPORT_ROLES = (
    OrganizationMembership.Role.OWNER,
    OrganizationMembership.Role.PROPERTY_MANAGER,
    OrganizationMembership.Role.ACCOUNTANT,
)


def expected_accounts(charge_type):
    normalized = (charge_type or '').strip().upper()

    if normalized in DEPOSIT_CHARGE_TYPES:
        return '1100', '2100'
    if normalized in ('RENT', 'BASE_RENT'):
        return '1100', '4010'
    if normalized in CHARGE_TYPES:
        return '1100', '4020'

    return None


def journal_status(charge, entries):
    """Reconcile original entries and any reversals without writing data."""
    originals = [entry for entry in entries if entry.reverses_id is None]
    reversals = [entry for entry in entries if entry.reverses_id is not None]
    expected = expected_accounts(charge.charge_type)

    if (
        charge.organization_id != charge.invoice.organization_id
        or charge.tenant_id != charge.invoice.tenant_id
    ):
        return 'INCONSISTENT'

    if expected is None:
        return 'INCONSISTENT'

    if not originals:
        return 'MISSING'

    debit_account, credit_account = expected
    actual = sorted(
        (entry.account, entry.direction, entry.amount_cents)
        for entry in originals
    )
    wanted = sorted((
        (debit_account, ChargeJournalEntry.Direction.DEBIT, charge.amount_cents),
        (credit_account, ChargeJournalEntry.Direction.CREDIT, charge.amount_cents),
    ))

    if len(originals) != 2 or actual != wanted:
        return 'INCONSISTENT'

    debit_total = sum(
        entry.amount_cents for entry in originals
        if entry.direction == ChargeJournalEntry.Direction.DEBIT
    )
    credit_total = sum(
        entry.amount_cents for entry in originals
        if entry.direction == ChargeJournalEntry.Direction.CREDIT
    )
    if debit_total != credit_total:
        return 'INCONSISTENT'

    originals_by_id = {entry.pk: entry for entry in originals}
    reversed_ids = set()

    for reversal in reversals:
        original = originals_by_id.get(reversal.reverses_id)
        if original is None or reversal.reverses_id in reversed_ids:
            return 'INCONSISTENT'

        expected_direction = (
            ChargeJournalEntry.Direction.CREDIT
            if original.direction == ChargeJournalEntry.Direction.DEBIT
            else ChargeJournalEntry.Direction.DEBIT
            if original.direction == ChargeJournalEntry.Direction.CREDIT
            else None
        )

        if (
            expected_direction is None
            or reversal.account != original.account
            or reversal.amount_cents != original.amount_cents
            or reversal.direction != expected_direction
        ):
            return 'INCONSISTENT'

        reversed_ids.add(original.pk)

    return 'OK'


class ChargeJournalReportView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    http_method_names = ('get', 'head', 'options')

    def get(self, request):
        organization_value = request.query_params.get('organization')

        if not organization_value:
            raise ValidationError({
                'organization': 'An organization ID is required.',
            })

        try:
            organization_id = int(organization_value)
        except (TypeError, ValueError) as error:
            raise ValidationError({
                'organization': 'A valid organization ID is required.',
            }) from error

        has_access = OrganizationMembership.objects.filter(
            user=request.user,
            organization_id=organization_id,
            is_active=True,
            organization__is_active=True,
            role__in=REPORT_ROLES,
        ).exists()

        if not has_access:
            raise PermissionDenied(
                'You do not have permission to view this organization’s financial reports.'
            )

        charges = (
            Charge.objects.filter(
                organization_id=organization_id,
                lifecycle=DocumentStatus.POSTED,
                invoice__status=DocumentStatus.POSTED,
                currency='KES',
            )
            .select_related('invoice')
            .prefetch_related(
                Prefetch(
                    'journal_entries',
                    queryset=ChargeJournalEntry.objects.order_by('pk'),
                    to_attr='report_journal_entries',
                )
            )
            .order_by('created_at', 'pk')
        )

        results = []
        counts = defaultdict(int)

        for charge in charges:
            entries = charge.report_journal_entries
            reconciliation_status = journal_status(charge, entries)
            counts[reconciliation_status] += 1

            results.append({
                'charge_id': str(charge.pk),
                'invoice_id': charge.invoice_id,
                'organization_id': charge.organization_id,
                'charge_type': charge.charge_type,
                'currency': charge.currency,
                'amount_cents': charge.amount_cents,
                'status': reconciliation_status,
                'journal_entries': [
                    {
                        'id': entry.pk,
                        'account': entry.account,
                        'direction': entry.direction,
                        'amount_cents': entry.amount_cents,
                        'reverses_id': entry.reverses_id,
                        'created_at': entry.created_at.isoformat(),
                    }
                    for entry in entries
                ],
            })

        return Response({
            'organization_id': organization_id,
            'currency': 'KES',
            'summary': {
                'inspected': len(results),
                'ok': counts['OK'],
                'missing': counts['MISSING'],
                'inconsistent': counts['INCONSISTENT'],
            },
            'results': results,
        })
