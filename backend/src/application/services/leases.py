from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.leases.models import Lease, LeaseAmendment
from apps.properties.models import Unit
from application.services.audit import record_audit
from application.services.notifications import notify_user
from common.rental_dates import rental_business_date


def _save_clean(lease, fields):
    try:
        lease.full_clean()
    except DjangoValidationError as error:
        if getattr(error, 'message_dict', None):
            raise ValidationError(error.message_dict) from error
        raise ValidationError(error.messages) from error
    lease.save(update_fields=fields)


def _release_unit_if_idle(unit):
    today = rental_business_date()
    still_active = unit.leases.filter(status=Lease.Status.ACTIVE).exists() or unit.leases.filter(
        status=Lease.Status.TERMINATED,
        start_date__lte=today,
        end_date__gte=today,
    ).exists()
    if not still_active and unit.status == Unit.Status.OCCUPIED:
        unit.status = Unit.Status.AVAILABLE
        unit.save(update_fields=('status', 'updated_at'))


def _lock_lease_and_unit(lease):
    unit_id = Lease.objects.values_list('unit_id', flat=True).get(pk=lease.pk)
    unit = Unit.objects.select_for_update().get(pk=unit_id)
    locked = Lease.objects.select_for_update().select_related('tenant', 'tenant__user').get(pk=lease.pk)
    if locked.unit_id != unit.pk:
        raise ValidationError({'unit': 'Lease unit changed concurrently; reload and retry.'})
    return locked, unit


@transaction.atomic
def activate_lease(lease, *, actor, request=None):
    lease, unit = _lock_lease_and_unit(lease)
    if lease.status != Lease.Status.DRAFT:
        raise ValidationError({'status': 'Only a draft lease can be activated.'})
    lease.status = Lease.Status.ACTIVE
    _save_clean(lease, ('status', 'updated_at'))
    unit.status = Unit.Status.OCCUPIED
    unit.save(update_fields=('status', 'updated_at'))
    organization = lease.tenant.organization
    record_audit(
        action='lease.activate',
        object_type='Lease',
        object_id=lease.pk,
        actor=actor,
        organization=organization,
        metadata={'unit_id': unit.pk, 'tenant_id': lease.tenant_id},
        request=request,
    )
    notify_user(
        user=lease.tenant.user,
        type='LEASE_ACTIVATED',
        title='Lease activated',
        body=f'Lease {lease.reference} is now active.',
        organization=organization,
        payload={'lease_id': lease.pk, 'unit_id': unit.pk},
    )
    return lease


@transaction.atomic
def terminate_lease(lease, *, end_date, reason, actor, request=None):
    lease, unit = _lock_lease_and_unit(lease)
    if lease.status == Lease.Status.TERMINATED and lease.end_date == end_date:
        return lease
    if lease.status != Lease.Status.ACTIVE:
        raise ValidationError({'status': 'Only an active lease can be terminated.'})
    if end_date <= lease.start_date:
        raise ValidationError({'end_date': 'End date must be after the lease start date.'})
    today = rental_business_date()
    if end_date > today:
        raise ValidationError({
            'end_date': (
                'Termination is effective immediately and cannot release a unit before its final inclusive day. '
                'Use a future lease or amendment workflow to schedule a later change.'
            ),
        })

    prior_termination = LeaseAmendment.objects.filter(
        lease=lease,
        amendment_type=LeaseAmendment.AmendmentType.TERMINATION,
    ).order_by('-created_at', '-pk').first()
    if prior_termination is not None:
        if prior_termination.effective_date == end_date:
            return lease
        raise ValidationError({'end_date': 'A termination date is already recorded for this lease.'})

    ends_today = end_date == today
    before = {
        'status': lease.status,
        'end_date': lease.end_date.isoformat() if lease.end_date else None,
    }
    if not ends_today:
        # A past inclusive end date represents an explicitly authorized early
        # termination. A termination dated today stays active through the end
        # of the Nairobi civil day.
        lease.status = Lease.Status.TERMINATED
    lease.end_date = end_date
    fields = ('end_date', 'updated_at') if ends_today else ('status', 'end_date', 'updated_at')
    _save_clean(lease, fields)
    LeaseAmendment.objects.create(
        lease=lease,
        amendment_type=LeaseAmendment.AmendmentType.TERMINATION,
        effective_date=end_date,
        reason=reason or '',
        before_state=before,
        after_state={'status': lease.status, 'end_date': end_date.isoformat()},
        created_by=actor,
    )
    if not ends_today:
        _release_unit_if_idle(unit)
    organization = lease.tenant.organization
    record_audit(
        action='lease.termination_scheduled' if ends_today else 'lease.terminate',
        object_type='Lease',
        object_id=lease.pk,
        actor=actor,
        organization=organization,
        metadata={
            'end_date': end_date.isoformat(),
            'reason': reason or '',
            'effective_after_inclusive_day': ends_today,
        },
        request=request,
    )
    if ends_today:
        notify_user(
            user=lease.tenant.user,
            type='LEASE_END_SCHEDULED',
            title='Lease end scheduled',
            body=f'Lease {lease.reference} remains active through {end_date.isoformat()}.',
            organization=organization,
            payload={'lease_id': lease.pk, 'end_date': end_date.isoformat()},
        )
    else:
        notify_user(
            user=lease.tenant.user,
            type='LEASE_TERMINATED',
            title='Lease terminated',
            body=f'Lease {lease.reference} was terminated.',
            organization=organization,
            payload={'lease_id': lease.pk, 'end_date': end_date.isoformat()},
        )
    return lease


@transaction.atomic
def expire_lease(lease, *, actor, request=None, business_date=None, source='manual'):
    lease, unit = _lock_lease_and_unit(lease)
    if lease.status in (Lease.Status.TERMINATED, Lease.Status.EXPIRED):
        _release_unit_if_idle(unit)
        return lease
    if lease.status != Lease.Status.ACTIVE:
        raise ValidationError({'status': 'Only an active lease can expire.'})
    today = business_date or rental_business_date()
    if lease.end_date is None or lease.end_date >= today:
        raise ValidationError({'end_date': 'The lease end date must be before today.'})
    scheduled_termination = LeaseAmendment.objects.filter(
        lease=lease,
        amendment_type=LeaseAmendment.AmendmentType.TERMINATION,
        effective_date=lease.end_date,
    ).exists()
    lease.status = Lease.Status.TERMINATED if scheduled_termination else Lease.Status.EXPIRED
    _save_clean(lease, ('status', 'updated_at'))
    _release_unit_if_idle(unit)
    record_audit(
        action='lease.terminate' if scheduled_termination else 'lease.expire',
        object_type='Lease',
        object_id=lease.pk,
        actor=actor,
        organization=lease.tenant.organization,
        metadata={'end_date': lease.end_date.isoformat(), 'source': source},
        request=request,
    )
    if scheduled_termination:
        notify_user(
            user=lease.tenant.user,
            type='LEASE_TERMINATED',
            title='Lease terminated',
            body=f'Lease {lease.reference} ended after its final inclusive day.',
            organization=lease.tenant.organization,
            payload={'lease_id': lease.pk, 'end_date': lease.end_date.isoformat()},
        )
    return lease


def expire_due_leases(*, as_of=None):
    """Finalize leases after their inclusive Nairobi end date has passed.

    Each lease is finalized through ``expire_lease`` in its own transaction.
    Failures are returned for command-level reporting and can be retried on
    the next scheduled run without repeating completed notifications.
    """
    today = as_of or rental_business_date()
    due_lease_ids = list(
        Lease.objects.filter(
            status=Lease.Status.ACTIVE,
            end_date__lt=today,
        ).order_by('end_date', 'pk').values_list('pk', flat=True)
    )
    processed = 0
    failures = []
    for lease_id in due_lease_ids:
        try:
            lease = Lease.objects.get(pk=lease_id)
            expire_lease(
                lease,
                actor=None,
                business_date=today,
                source='scheduled_expiry',
            )
        except Lease.DoesNotExist:
            continue
        except Exception as error:
            failures.append((lease_id, error))
        else:
            processed += 1
    return processed, failures
