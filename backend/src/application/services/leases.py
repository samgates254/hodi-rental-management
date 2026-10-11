from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.leases.models import Lease, LeaseAmendment
from apps.properties.models import Unit
from application.services.audit import record_audit
from application.services.notifications import notify_user


def _save_clean(lease, fields):
    try:
        lease.full_clean()
    except DjangoValidationError as error:
        if getattr(error, 'message_dict', None):
            raise ValidationError(error.message_dict) from error
        raise ValidationError(error.messages) from error
    lease.save(update_fields=fields)


def _release_unit_if_idle(unit):
    still_active = unit.leases.filter(status=Lease.Status.ACTIVE).exists()
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
    if lease.status != Lease.Status.ACTIVE:
        raise ValidationError({'status': 'Only an active lease can be terminated.'})
    if end_date <= lease.start_date:
        raise ValidationError({'end_date': 'End date must be after the lease start date.'})
    before = {
        'status': lease.status,
        'end_date': lease.end_date.isoformat() if lease.end_date else None,
    }
    lease.status = Lease.Status.TERMINATED
    lease.end_date = end_date
    _save_clean(lease, ('status', 'end_date', 'updated_at'))
    LeaseAmendment.objects.create(
        lease=lease,
        amendment_type=LeaseAmendment.AmendmentType.TERMINATION,
        effective_date=end_date,
        reason=reason or '',
        before_state=before,
        after_state={'status': lease.status, 'end_date': end_date.isoformat()},
        created_by=actor,
    )
    _release_unit_if_idle(unit)
    organization = lease.tenant.organization
    record_audit(
        action='lease.terminate',
        object_type='Lease',
        object_id=lease.pk,
        actor=actor,
        organization=organization,
        metadata={'end_date': end_date.isoformat(), 'reason': reason or ''},
        request=request,
    )
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
def expire_lease(lease, *, actor, request=None):
    lease, unit = _lock_lease_and_unit(lease)
    if lease.status != Lease.Status.ACTIVE:
        raise ValidationError({'status': 'Only an active lease can expire.'})
    today = timezone.localdate()
    if lease.end_date is None or lease.end_date >= today:
        raise ValidationError({'end_date': 'The lease end date must be before today.'})
    lease.status = Lease.Status.EXPIRED
    _save_clean(lease, ('status', 'updated_at'))
    _release_unit_if_idle(unit)
    record_audit(
        action='lease.expire',
        object_type='Lease',
        object_id=lease.pk,
        actor=actor,
        organization=lease.tenant.organization,
        metadata={'end_date': lease.end_date.isoformat()},
        request=request,
    )
    return lease
