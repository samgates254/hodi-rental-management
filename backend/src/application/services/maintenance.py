from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.leases.models import Lease
from apps.maintenance.models import (
    MaintenanceIssue,
    MaintenanceIssueUpdate,
    MaintenanceComment,
    MaintenanceRequest,
    TechnicianProfile,
    WorkOrder,
)
from apps.organizations.models import OrganizationMembership
from application.services.audit import record_audit
from application.services.notifications import notify_user
from engines.maintenance.priority.facade import score
from rental_os.algorithms.matching import Job, Technician
from rental_os.algorithms.priority import PriorityError
from rental_os.algorithms.matching import MatchingError


OPEN_FOR_EDIT = {MaintenanceRequest.Status.OPEN, MaintenanceRequest.Status.IN_PROGRESS}


def _sync_legacy_issue(maintenance_request, *, actor, status, note=''):
    issue = MaintenanceIssue.objects.select_for_update().filter(operational_request=maintenance_request).first()
    if issue is None:
        return
    issue.status = status
    issue.resolved_at = timezone.now() if status == MaintenanceIssue.Status.RESOLVED else None
    issue.save(update_fields=('status', 'resolved_at', 'updated_at'))
    MaintenanceIssueUpdate.objects.create(issue=issue, author=actor, status=status, note=note)


def _ensure_legacy_issue(maintenance_request, *, actor):
    if maintenance_request.tenant_id is None:
        return None
    issue = MaintenanceIssue.objects.filter(operational_request=maintenance_request).first()
    if issue is not None:
        return issue
    priority = _legacy_priority_for_hazard(maintenance_request.hazard)
    issue = MaintenanceIssue.objects.create(
        tenant=maintenance_request.tenant,
        unit=maintenance_request.unit,
        title=maintenance_request.title,
        category='OTHER',
        priority=priority,
        description=maintenance_request.description,
        operational_request=maintenance_request,
    )
    MaintenanceIssueUpdate.objects.create(issue=issue, author=actor, status=issue.status, note='Issue created')
    return issue


def _legacy_priority_for_hazard(hazard):
    if hazard >= 5:
        return MaintenanceIssue.Priority.URGENT
    if hazard >= 4:
        return MaintenanceIssue.Priority.HIGH
    if hazard <= 2:
        return MaintenanceIssue.Priority.LOW
    return MaintenanceIssue.Priority.NORMAL


def score_maintenance(*, hazard, vulnerability, building_age_years=None, age_band_value=None):
    if building_age_years is None and age_band_value is None:
        age_band_value = 3
    try:
        if building_age_years is not None:
            return score(
                hazard=hazard,
                vulnerability=vulnerability,
                building_age_years=building_age_years,
                age_band_value=None,
            )
        return score(
            hazard=hazard,
            vulnerability=vulnerability,
            building_age_years=None,
            age_band_value=age_band_value,
        )
    except PriorityError as error:
        raise ValidationError({'hazard': str(error)}) from error


def _active_lease(tenant, unit, today):
    return Lease.objects.filter(
        tenant=tenant,
        unit=unit,
        status=Lease.Status.ACTIVE,
        start_date__lte=today,
    ).filter(
        models_q_end(today),
    ).exists()


def models_q_end(today):
    from django.db.models import Q
    return Q(end_date__isnull=True) | Q(end_date__gte=today)


@transaction.atomic
def create_request(
    *,
    unit,
    title,
    description,
    hazard,
    actor,
    tenant=None,
    vulnerability=1,
    building_age_years=None,
    age_band_value=None,
    request=None,
):
    if tenant is not None and tenant.organization_id != unit.organization_id:
        raise ValidationError({'unit': 'Tenant and unit must belong to the same organization.'})
    if tenant is not None and tenant.user_id == actor.id:
        today = timezone.localdate()
        if not _active_lease(tenant, unit, today):
            raise ValidationError({'unit': 'The unit must be on your active lease.'})
    result = score_maintenance(
        hazard=hazard,
        vulnerability=vulnerability,
        building_age_years=building_age_years,
        age_band_value=age_band_value,
    )
    maintenance_request = MaintenanceRequest.objects.create(
        unit=unit,
        tenant=tenant,
        created_by=actor,
        title=title,
        description=description,
        hazard=int(result.hazard),
        vulnerability=result.vulnerability,
        status=MaintenanceRequest.Status.OPEN,
        priority_class=result.priority_class,
        score_millis=result.score_millis,
        emergency_override=result.emergency_override,
    )
    WorkOrder.objects.create(request=maintenance_request, status=WorkOrder.Status.PENDING)
    record_audit(
        action='maintenance.create',
        object_type='MaintenanceRequest',
        object_id=maintenance_request.pk,
        actor=actor,
        organization=unit.building.property.organization,
        metadata={
            'priority_class': result.priority_class,
            'emergency_override': result.emergency_override,
            'unit_id': unit.pk,
        },
        request=request,
    )
    return maintenance_request


@transaction.atomic
def update_request(maintenance_request, *, validated_data, actor, request=None):
    maintenance_request = MaintenanceRequest.objects.select_for_update().get(pk=maintenance_request.pk)
    if maintenance_request.status not in OPEN_FOR_EDIT:
        raise ValidationError({'status': 'Completed or closed requests cannot be edited.'})
    for field in ('title', 'description', 'hazard', 'vulnerability'):
        if field in validated_data:
            setattr(maintenance_request, field, validated_data[field])
    building_age_years = validated_data.get('building_age_years')
    age_band_value = validated_data.get('age_band_value')
    if 'hazard' in validated_data or 'vulnerability' in validated_data or building_age_years or age_band_value:
        result = score_maintenance(
            hazard=maintenance_request.hazard,
            vulnerability=maintenance_request.vulnerability,
            building_age_years=building_age_years,
            age_band_value=age_band_value,
        )
        maintenance_request.hazard = int(result.hazard)
        maintenance_request.vulnerability = result.vulnerability
        maintenance_request.priority_class = result.priority_class
        maintenance_request.score_millis = result.score_millis
        maintenance_request.emergency_override = result.emergency_override
    maintenance_request.full_clean()
    maintenance_request.save()
    issue = MaintenanceIssue.objects.select_for_update().filter(
        operational_request=maintenance_request,
    ).first()
    if issue is not None:
        if (issue.tenant_id != maintenance_request.tenant_id
                or issue.unit_id != maintenance_request.unit_id
                or issue.organization_id != maintenance_request.organization_id):
            raise ValidationError({'detail': 'Linked maintenance records have inconsistent ownership.'})
        changed_fields = []
        for field in ('title', 'description'):
            value = getattr(maintenance_request, field)
            if getattr(issue, field) != value:
                setattr(issue, field, value)
                changed_fields.append(field)
        priority = _legacy_priority_for_hazard(maintenance_request.hazard)
        if issue.priority != priority:
            issue.priority = priority
            changed_fields.append('priority')
        if changed_fields:
            issue.save(update_fields=tuple(changed_fields + ['updated_at']))
            MaintenanceIssueUpdate.objects.create(
                issue=issue, author=actor, status=issue.status,
                note='Request details updated: ' + ', '.join(changed_fields),
            )
    record_audit(
        action='maintenance.update', object_type='MaintenanceRequest',
        object_id=maintenance_request.pk, actor=actor,
        organization=maintenance_request.unit.building.property.organization,
        metadata={'updated_fields': sorted(validated_data.keys()), 'linked_issue': issue is not None},
        request=request,
    )
    return maintenance_request


@transaction.atomic
def assign_request(maintenance_request, *, assignee, actor, notes='', request=None):
    maintenance_request = (
        MaintenanceRequest.objects.select_for_update(
            of=('self', 'unit', 'unit__building', 'unit__building__property'),
        )
        .select_related('unit__building__property', 'tenant__user')
        .get(pk=maintenance_request.pk)
    )
    if maintenance_request.status in (
        MaintenanceRequest.Status.COMPLETED,
        MaintenanceRequest.Status.CLOSED,
        MaintenanceRequest.Status.CANCELLED,
    ):
        raise ValidationError({'status': 'This request can no longer be assigned.'})
    work_order = WorkOrder.objects.select_for_update().get(request=maintenance_request)
    work_order.assignee = assignee
    work_order.status = WorkOrder.Status.ASSIGNED
    work_order.assigned_at = timezone.now()
    if notes:
        work_order.notes = notes
    work_order.save()
    maintenance_request.status = MaintenanceRequest.Status.IN_PROGRESS
    maintenance_request.save(update_fields=('status', 'updated_at'))
    _sync_legacy_issue(maintenance_request, actor=actor, status=MaintenanceIssue.Status.IN_PROGRESS, note=notes)
    organization = maintenance_request.unit.building.property.organization
    record_audit(
        action='maintenance.assign',
        object_type='MaintenanceRequest',
        object_id=maintenance_request.pk,
        actor=actor,
        organization=organization,
        metadata={'assignee_id': assignee.pk, 'work_order_id': work_order.pk},
        request=request,
    )
    notify_user(
        user=assignee,
        type='MAINTENANCE_ASSIGNED',
        title='Maintenance assigned',
        body=maintenance_request.title,
        organization=organization,
        payload={'request_id': maintenance_request.pk, 'work_order_id': work_order.pk},
    )
    return maintenance_request


@transaction.atomic
def complete_request(maintenance_request, *, actor, notes='', request=None):
    maintenance_request = (
        MaintenanceRequest.objects.select_for_update(
            of=(
                'self',
                'unit',
                'unit__building',
                'unit__building__property',
                'created_by',
            ),
        )
        .select_related('unit__building__property', 'tenant__user', 'created_by')
        .get(pk=maintenance_request.pk)
    )
    if maintenance_request.status in (
        MaintenanceRequest.Status.COMPLETED,
        MaintenanceRequest.Status.CLOSED,
        MaintenanceRequest.Status.CANCELLED,
    ):
        raise ValidationError({'status': 'This request is already finished.'})
    work_order = WorkOrder.objects.select_for_update().get(request=maintenance_request)
    if work_order.assignee_id is not None and work_order.assignee_id != actor.id:
        from common.permissions import user_can_access_organization_resource
        if not user_can_access_organization_resource(
            actor,
            maintenance_request.organization_id,
            'maintenance',
            'write',
        ):
            raise PermissionDenied('Only the assignee or maintenance staff can complete this request.')
    now = timezone.now()
    work_order.status = WorkOrder.Status.COMPLETED
    work_order.completed_at = now
    if notes:
        work_order.notes = notes
    work_order.save()
    maintenance_request.status = MaintenanceRequest.Status.COMPLETED
    maintenance_request.completed_at = now
    maintenance_request.save(update_fields=('status', 'completed_at', 'updated_at'))
    _sync_legacy_issue(maintenance_request, actor=actor, status=MaintenanceIssue.Status.RESOLVED, note=notes)
    organization = maintenance_request.unit.building.property.organization
    record_audit(
        action='maintenance.complete',
        object_type='MaintenanceRequest',
        object_id=maintenance_request.pk,
        actor=actor,
        organization=organization,
        metadata={'work_order_id': work_order.pk},
        request=request,
    )
    recipient = maintenance_request.tenant.user if maintenance_request.tenant_id else maintenance_request.created_by
    notify_user(
        user=recipient,
        type='MAINTENANCE_UPDATED',
        title='Maintenance completed',
        body=maintenance_request.title,
        organization=organization,
        payload={'request_id': maintenance_request.pk, 'status': maintenance_request.status},
    )
    return maintenance_request


@transaction.atomic
def close_request(maintenance_request, *, actor, request=None):
    maintenance_request = (
        MaintenanceRequest.objects.select_for_update()
        .select_related('unit__building__property')
        .get(pk=maintenance_request.pk)
    )
    if maintenance_request.status != MaintenanceRequest.Status.COMPLETED:
        raise ValidationError({'status': 'Complete the request before closing it.'})
    now = timezone.now()
    maintenance_request.status = MaintenanceRequest.Status.CLOSED
    maintenance_request.closed_at = now
    maintenance_request.save(update_fields=('status', 'closed_at', 'updated_at'))
    _sync_legacy_issue(maintenance_request, actor=actor, status=MaintenanceIssue.Status.RESOLVED, note='Request closed')
    organization = maintenance_request.unit.building.property.organization
    record_audit(
        action='maintenance.close',
        object_type='MaintenanceRequest',
        object_id=maintenance_request.pk,
        actor=actor,
        organization=organization,
        metadata={},
        request=request,
    )
    return maintenance_request


@transaction.atomic
def add_comment(maintenance_request, *, author, body):
    if not (body or '').strip():
        raise ValidationError({'body': 'A comment is required.'})
    return MaintenanceComment.objects.create(
        request=maintenance_request,
        author=author,
        body=body.strip(),
    )


def preview_matches(*, organization, jobs):
    memberships = OrganizationMembership.objects.filter(
        organization=organization,
        role=OrganizationMembership.Role.TECHNICIAN,
        is_active=True,
        organization__is_active=True,
    ).select_related('user', 'user__account_profile', 'user__technician_profile')
    technicians = []
    for membership in memberships:
        profile = TechnicianProfile.objects.filter(user=membership.user).first()
        trade = ''
        account = getattr(membership.user, 'account_profile', None)
        if account is not None:
            trade = account.professional_trade or ''
        skills = []
        if profile is not None:
            skills = [str(skill).strip().upper() for skill in (profile.skills or []) if str(skill).strip()]
            if profile.trade:
                skills.append(profile.trade.strip().upper())
        elif trade:
            skills = [trade.strip().upper()]
        skills = tuple(dict.fromkeys(skills))
        rating = profile.rating_milli if profile is not None else 4000
        acceptance = profile.acceptance_milli if profile is not None else 800
        verified = profile.verified if profile is not None else False
        available = profile.available if profile is not None else False
        technicians.append(Technician(
            technician_id=str(membership.user_id),
            skills=skills,
            rating_milli=int(rating),
            acceptance_milli=int(acceptance),
            verified=verified,
            available=available,
        ))
    if not jobs:
        return {'assignments': [], 'unmatched_job_ids': []}
    if not technicians:
        return {
            'assignments': [],
            'unmatched_job_ids': [job['job_id'] for job in jobs],
        }
    engine_jobs = []
    for job in jobs:
        job_id = str(job['job_id']).strip()
        if not job_id:
            raise ValidationError({'jobs': 'job_id is required.'})
        skills = tuple(str(skill).strip().upper() for skill in job.get('required_skills', []) if str(skill).strip())
        distance = job.get('distance_m', 1000)
        if isinstance(distance, bool) or not isinstance(distance, int) or distance < 0:
            raise ValidationError({'jobs': 'distance_m must be an integer >= 0.'})
        distances = tuple((tech.technician_id, distance) for tech in technicians)
        per_tech = job.get('distances') or {}
        if per_tech:
            distances = tuple(
                (tech.technician_id, int(per_tech.get(tech.technician_id, distance)))
                for tech in technicians
            )
        engine_jobs.append(Job(
            job_id=job_id,
            required_skills=skills,
            distance_m_by_technician=distances,
        ))
    try:
        from engines.maintenance.technician_matching.facade import match
        result = match(jobs=engine_jobs, technicians=technicians)
    except MatchingError as error:
        raise ValidationError({'detail': str(error)}) from error
    return {
        'assignments': [
            {
                'job_id': row.job_id,
                'technician_id': row.technician_id,
                'weight_micro': row.weight_micro,
            }
            for row in result.assignments
        ],
        'unmatched_job_ids': list(result.unmatched_job_ids),
    }
