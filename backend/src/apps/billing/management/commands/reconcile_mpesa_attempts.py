from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.billing.models import MpesaAttempt
from application.services.audit import record_audit
from application.services.mpesa_callback import (
    OPEN_STATUSES,
    classify_stk_query,
    settle_verified_stk_failure,
)
from infrastructure.payments.mpesa import MpesaClient, MpesaError


MAX_ATTEMPTS = 5
DEFAULT_LIMIT = 100


class Command(BaseCommand):
    help = 'Reconcile stale M-Pesa attempts with Daraja STK Query; successful attempts need receipt review.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--review-required', action='store_true')
        parser.add_argument('--stale-minutes', type=int, default=2)
        parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT)

    def handle(self, *args, **options):
        stale_minutes = options['stale_minutes']
        limit = options['limit']
        if not 1 <= limit <= 1000 or (not options['review_required'] and stale_minutes < 1):
            self.stderr.write(self.style.ERROR('stale-minutes must be positive and limit must be 1..1000'))
            return
        if options['review_required']:
            review = MpesaAttempt.objects.filter(
                Q(reconciliation_state__in=(
                    MpesaAttempt.ReconciliationState.SUCCESS_NEEDS_RECEIPT,
                    MpesaAttempt.ReconciliationState.EXHAUSTED,
                )) | Q(status__in=OPEN_STATUSES, checkout_request_id__isnull=True)
                | Q(status__in=OPEN_STATUSES, merchant_request_id__isnull=True),
            ).order_by('last_reconciliation_at')[:limit]
            for attempt in review:
                self.stdout.write(
                    f'{attempt.pk} state={attempt.reconciliation_state} '
                    f'queries={attempt.reconciliation_attempts} '
                    f'checkout={attempt.checkout_request_id or "missing"} '
                    f'amount_cents={attempt.amount_cents}'
                )
            self.stdout.write(f'{len(review)} attempt(s) require operator review; no provider calls made.')
            return
        now = timezone.now()
        eligible = MpesaAttempt.objects.filter(
            status__in=OPEN_STATUSES,
            checkout_request_id__isnull=False,
            merchant_request_id__isnull=False,
            created_at__lte=now - timedelta(minutes=stale_minutes),
            reconciliation_attempts__lt=MAX_ATTEMPTS,
        ).filter(
            models_retry_due(now),
        ).order_by('last_reconciliation_at', 'created_at')
        attempts = list(eligible.select_related('organization', 'tenant', 'initiated_by')[:limit])
        if options['dry_run']:
            self.stdout.write(f'{len(attempts)} stale M-Pesa attempt(s) eligible; no provider calls made.')
            return

        client = MpesaClient.from_settings()
        counts = {'SUCCESS_NEEDS_RECEIPT': 0, 'FAILED': 0, 'UNRESOLVED': 0, 'SKIPPED': 0}
        for snapshot in attempts:
            try:
                query = client.stk_query(checkout_request_id=snapshot.checkout_request_id)
                outcome, result_code, description = classify_stk_query(snapshot, query)
            except MpesaError:
                outcome, result_code, description = 'UNRESOLVED', '', ''
            with transaction.atomic():
                current = MpesaAttempt.objects.select_for_update().select_related(
                    'organization', 'initiated_by',
                ).get(pk=snapshot.pk)
                if current.status not in OPEN_STATUSES:
                    counts['SKIPPED'] += 1
                    continue
                current.reconciliation_attempts += 1
                current.last_reconciliation_at = timezone.now()
                if outcome == 'SUCCESS':
                    # STK Query does not return the M-Pesa receipt metadata required
                    # by Payment idempotency/reconciliation. Never fabricate it.
                    current.reconciliation_state = MpesaAttempt.ReconciliationState.SUCCESS_NEEDS_RECEIPT
                    counts['SUCCESS_NEEDS_RECEIPT'] += 1
                elif outcome == 'FAILED':
                    current.reconciliation_state = MpesaAttempt.ReconciliationState.PROVIDER_FAILED
                    counts['FAILED'] += 1
                else:
                    current.reconciliation_state = MpesaAttempt.ReconciliationState.UNRESOLVED
                    counts['UNRESOLVED'] += 1
                if current.reconciliation_attempts >= MAX_ATTEMPTS and outcome == 'UNRESOLVED':
                    current.reconciliation_state = MpesaAttempt.ReconciliationState.EXHAUSTED
                current.save(update_fields=(
                    'reconciliation_attempts', 'last_reconciliation_at', 'reconciliation_state', 'updated_at',
                ))
                if outcome == 'FAILED':
                    settle_verified_stk_failure(
                        checkout_request_id=current.checkout_request_id,
                        merchant_request_id=current.merchant_request_id,
                        result_code=result_code,
                        result_description=description,
                        provider_query=query,
                    )
                record_audit(
                    action='mpesa.stk.reconcile', object_type='MpesaAttempt', object_id=current.pk,
                    actor=None, organization=current.organization,
                    metadata={
                        'outcome': outcome,
                        'attempt_number': current.reconciliation_attempts,
                        'provider_result_code': result_code or None,
                        'review_required': outcome == 'SUCCESS',
                    },
                )
        self.stdout.write('Reconciliation complete: ' + ', '.join(f'{key}={value}' for key, value in counts.items()))


def models_retry_due(now):
    # Exponential backoff: 2, 4, 8, 16, then 32 minutes between queries.
    due = Q(reconciliation_attempts=0, last_reconciliation_at__isnull=True)
    for attempt_count in range(1, MAX_ATTEMPTS + 1):
        delay = 2 ** attempt_count
        due |= Q(
            reconciliation_attempts=attempt_count,
            last_reconciliation_at__lte=now - timedelta(minutes=delay),
        )
    return due
