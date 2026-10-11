from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.leases.models import Lease
from apps.maintenance.models import (
    MaintenanceIssue,
    MaintenanceIssueUpdate,
    MaintenanceComment,
    MaintenanceRequest,
    RepairCompletion,
    RepairMaterialUsed,
    RepairQuotation,
    TechnicianProfile,
    WorkOrderAssignment,
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
        category=maintenance_request.category,
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


def _required_skills_for_category(category):
    normalized = (category or '').strip().upper()
    return {
        'PLUMBING': ('PLUMBER',),
        'ELECTRICAL': ('ELECTRICIAN',),
        'CARPENTRY': ('CARPENTER',),
        'HVAC': ('HVAC',),
        'MASONRY': ('MASON',),
    }.get(normalized, () if normalized in ('', 'OTHER') else (normalized,))


def _validate_technician(maintenance_request, user):
    membership = OrganizationMembership.objects.filter(
        user=user, organization_id=maintenance_request.organization_id,
        organization__is_active=True, is_active=True,
        role=OrganizationMembership.Role.TECHNICIAN,
    ).first()
    profile = TechnicianProfile.objects.filter(user=user).first()
    if (membership is None or not user.is_active or profile is None
            or not profile.verified or not profile.available):
        raise ValidationError({'assignee': 'Technician must be an active, verified and available organization member.'})
    required = _required_skills_for_category(maintenance_request.category)
    skills = tuple(str(value).strip().upper() for value in (profile.skills or []) if str(value).strip())
    if profile.trade:
        skills += (profile.trade.strip().upper(),)
    from engines.maintenance.technician_matching.facade import match
    result = match(
        jobs=[Job(job_id=str(maintenance_request.pk), required_skills=required,
                  distance_m_by_technician=((str(user.pk), 1000),))],
        technicians=[Technician(
            technician_id=str(user.pk), skills=skills,
            rating_milli=profile.rating_milli, acceptance_milli=profile.acceptance_milli,
            verified=profile.verified, available=profile.available,
        )],
    )
    if not result.assignments:
        raise ValidationError({'assignee': 'Technician is not eligible for this repair.'})
    return membership


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
    category='OTHER',
    requires_approval=False,
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
        category=category,
        hazard=int(result.hazard),
        vulnerability=result.vulnerability,
        status=MaintenanceRequest.Status.OPEN,
        priority_class=result.priority_class,
        score_millis=result.score_millis,
        emergency_override=result.emergency_override,
        requires_approval=requires_approval,
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
    membership = OrganizationMembership.objects.filter(
        user=assignee, organization_id=maintenance_request.organization_id,
        organization__is_active=True, is_active=True,
    ).first()
    if membership is None or not assignee.is_active:
        raise ValidationError({'assignee': 'Assignee must be an active member of this organization.'})
    if membership.role not in (
        OrganizationMembership.Role.OWNER,
        OrganizationMembership.Role.PROPERTY_MANAGER,
        OrganizationMembership.Role.CARETAKER,
        OrganizationMembership.Role.TECHNICIAN,
    ):
        raise ValidationError({'assignee': 'This organization role cannot be assigned maintenance work.'})
    if membership.role == OrganizationMembership.Role.TECHNICIAN:
        _validate_technician(maintenance_request, assignee)
    previous_assignee_id = work_order.assignee_id
    work_order.assignee = assignee
    work_order.status = WorkOrder.Status.ASSIGNED
    work_order.assigned_at = timezone.now()
    if notes:
        work_order.notes = notes
    work_order.save()
    WorkOrderAssignment.objects.create(
        work_order=work_order, previous_assignee_id=previous_assignee_id,
        new_assignee=assignee, actor=actor, notes=notes,
        status=(
            WorkOrderAssignment.Status.PENDING
            if membership.role == OrganizationMembership.Role.TECHNICIAN
            else WorkOrderAssignment.Status.NOT_REQUIRED
        ),
    )
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


def _lock_assignment_for_actor(row, order, actor):
    if order.assignee_id != actor.pk:
        raise PermissionDenied('Only the currently assigned technician can respond to this assignment.')
    _validate_technician(row, actor)
    assignment = WorkOrderAssignment.objects.select_for_update().filter(
        work_order=order, new_assignee=actor,
    ).order_by('-created_at', '-pk').first()
    if assignment is None:
        raise ValidationError({'assignment': 'The current assignment has no response record.'})
    return assignment


@transaction.atomic
def accept_assignment(maintenance_request, *, actor, request=None):
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(
        pk=maintenance_request.pk,
    )
    order = WorkOrder.objects.select_for_update().get(request=row)
    if row.status != MaintenanceRequest.Status.IN_PROGRESS or order.status not in (
        WorkOrder.Status.ASSIGNED, WorkOrder.Status.IN_PROGRESS,
    ):
        raise ValidationError({'status': 'Only a current assigned work order can be accepted.'})
    assignment = _lock_assignment_for_actor(row, order, actor)
    if assignment.status == WorkOrderAssignment.Status.ACCEPTED:
        return assignment
    if order.status != WorkOrder.Status.ASSIGNED:
        raise ValidationError({'status': 'Work has already started without an accepted assignment.'})
    if assignment.status != WorkOrderAssignment.Status.PENDING:
        raise ValidationError({'status': 'This assignment has already been declined.'})
    assignment.status = WorkOrderAssignment.Status.ACCEPTED
    assignment.responded_at = timezone.now()
    assignment.save(update_fields=('status', 'responded_at'))
    record_audit(
        action='maintenance.assignment_accepted', object_type='WorkOrderAssignment', object_id=assignment.pk,
        actor=actor, organization=row.unit.building.property.organization,
        metadata={'work_order_id': order.pk}, request=request,
    )
    return assignment


@transaction.atomic
def decline_assignment(maintenance_request, *, actor, reason, request=None):
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(
        pk=maintenance_request.pk,
    )
    order = WorkOrder.objects.select_for_update().get(request=row)
    if row.status != MaintenanceRequest.Status.IN_PROGRESS or order.status != WorkOrder.Status.ASSIGNED:
        raise ValidationError({'status': 'Only a current assigned work order can be declined.'})
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A decline reason is required.'})
    assignment = _lock_assignment_for_actor(row, order, actor)
    if assignment.status != WorkOrderAssignment.Status.PENDING:
        raise ValidationError({'status': 'Only an unanswered assignment can be declined.'})
    now = timezone.now()
    assignment.status = WorkOrderAssignment.Status.DECLINED
    assignment.responded_at = now
    assignment.decline_reason = reason.strip()
    assignment.save(update_fields=('status', 'responded_at', 'decline_reason'))
    order.assignee = None
    order.status = WorkOrder.Status.PENDING
    order.assigned_at = None
    order.save(update_fields=('assignee', 'status', 'assigned_at', 'updated_at'))
    row.status = MaintenanceRequest.Status.OPEN
    row.save(update_fields=('status', 'updated_at'))
    _sync_legacy_issue(row, actor=actor, status=MaintenanceIssue.Status.OPEN,
                       note=f'Assignment declined; reassignment required: {reason.strip()}')
    record_audit(
        action='maintenance.assignment_declined', object_type='WorkOrderAssignment', object_id=assignment.pk,
        actor=actor, organization=row.unit.building.property.organization,
        metadata={'work_order_id': order.pk, 'reason': reason.strip()}, request=request,
    )
    notify_user(
        user=assignment.actor, type='MAINTENANCE_ASSIGNMENT_DECLINED',
        title='Maintenance assignment declined', body=row.title,
        organization=row.unit.building.property.organization,
        payload={'request_id': row.pk, 'work_order_id': order.pk},
    )
    return assignment


@transaction.atomic
def triage_request(maintenance_request, *, actor, category, hazard, vulnerability,
                   notes='', safety_override=False, safety_override_reason='',
                   requires_approval=None, request=None):
    row = MaintenanceRequest.objects.select_for_update().get(pk=maintenance_request.pk)
    if row.status not in (MaintenanceRequest.Status.OPEN, MaintenanceRequest.Status.IN_PROGRESS):
        raise ValidationError({'status': 'Only open work can be triaged.'})
    result = score_maintenance(hazard=hazard, vulnerability=vulnerability)
    if safety_override and not safety_override_reason.strip():
        raise ValidationError({'safety_override_reason': 'A reason is required for a safety override.'})
    before = {'category': row.category, 'hazard': row.hazard, 'priority_class': row.priority_class}
    row.category = category.strip().upper()
    row.hazard = int(result.hazard)
    row.vulnerability = result.vulnerability
    row.priority_class = result.priority_class
    row.score_millis = result.score_millis
    row.emergency_override = result.emergency_override
    row.triage_notes = notes.strip()
    row.triaged_by = actor
    row.triaged_at = timezone.now()
    row.safety_override = safety_override
    row.safety_override_reason = safety_override_reason.strip() if safety_override else ''
    row.safety_override_by = actor if safety_override else None
    if requires_approval is not None:
        row.requires_approval = requires_approval
    row.save(update_fields=(
        'category', 'hazard', 'vulnerability', 'priority_class', 'score_millis',
        'emergency_override', 'triage_notes', 'triaged_by', 'triaged_at',
        'safety_override', 'safety_override_reason', 'safety_override_by', 'updated_at',
        'requires_approval',
    ))
    issue = MaintenanceIssue.objects.select_for_update().filter(operational_request=row).first()
    if issue is not None:
        issue.category = row.category
        issue.priority = _legacy_priority_for_hazard(row.hazard)
        issue.save(update_fields=('category', 'priority', 'updated_at'))
        MaintenanceIssueUpdate.objects.create(
            issue=issue, author=actor, status=issue.status,
            note=f'Triage updated: category={row.category}; priority class={row.priority_class}; {notes.strip()}'.strip(),
        )
    record_audit(
        action='maintenance.triage', object_type='MaintenanceRequest', object_id=row.pk,
        actor=actor, organization=row.unit.building.property.organization,
        metadata={'before': before, 'category': row.category, 'priority_class': row.priority_class,
                  'safety_override': row.safety_override,
                  'safety_override_reason': row.safety_override_reason if row.safety_override else None,
                  'requires_approval': row.requires_approval}, request=request,
    )
    return row


@transaction.atomic
def start_work(maintenance_request, *, actor, request=None):
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(
        pk=maintenance_request.pk,
    )
    work_order = WorkOrder.objects.select_for_update().get(request=row)
    if row.status != MaintenanceRequest.Status.IN_PROGRESS or work_order.assignee_id != actor.pk:
        raise PermissionDenied('Only the assigned technician can start this work.')
    if work_order.status not in (WorkOrder.Status.ASSIGNED, WorkOrder.Status.IN_PROGRESS):
        raise ValidationError({'status': 'This work order cannot be started in its current state.'})
    membership = OrganizationMembership.objects.filter(
        user=actor, organization_id=row.organization_id, organization__is_active=True, is_active=True,
    ).first()
    assignment = WorkOrderAssignment.objects.select_for_update().filter(
        work_order=work_order, new_assignee=actor,
    ).order_by('-created_at', '-pk').first()
    if membership and membership.role == OrganizationMembership.Role.TECHNICIAN:
        _validate_technician(row, actor)
        if assignment and assignment.status == WorkOrderAssignment.Status.DECLINED:
            raise ValidationError({'assignment': 'A declined assignment cannot be started.'})
        # Preserve older clients: explicitly starting pending work is an auditable acceptance.
        if assignment and assignment.status == WorkOrderAssignment.Status.PENDING:
            assignment.status = WorkOrderAssignment.Status.ACCEPTED
            assignment.responded_at = timezone.now()
            assignment.save(update_fields=('status', 'responded_at'))
            record_audit(
                action='maintenance.assignment_accepted', object_type='WorkOrderAssignment', object_id=assignment.pk,
                actor=actor, organization=row.unit.building.property.organization,
                metadata={'work_order_id': work_order.pk, 'accepted_by_starting_work': True}, request=request,
            )
    latest_quote = work_order.quotations.order_by('-created_at', '-pk').first()
    if row.requires_approval and not row.safety_override and (
        latest_quote is None or latest_quote.status != RepairQuotation.Status.APPROVED
    ):
        raise ValidationError({'detail': 'An approved quotation is required before work starts.'})
    if work_order.status == WorkOrder.Status.ASSIGNED:
        work_order.status = WorkOrder.Status.IN_PROGRESS
        work_order.save(update_fields=('status', 'updated_at'))
        record_audit(action='maintenance.work_started', object_type='WorkOrder', object_id=work_order.pk,
                     actor=actor, organization=row.unit.building.property.organization, metadata={}, request=request)
    return work_order


@transaction.atomic
def schedule_follow_up(maintenance_request, *, actor, follow_up_at, reason, assignee, request=None):
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(
        pk=maintenance_request.pk,
    )
    order = WorkOrder.objects.select_for_update().get(request=row)
    completion = RepairCompletion.objects.select_for_update().filter(work_order=order).order_by(
        '-submitted_at', '-pk',
    ).first()
    if row.status not in (MaintenanceRequest.Status.IN_PROGRESS, MaintenanceRequest.Status.COMPLETED):
        raise ValidationError({'status': 'Follow-up can only be scheduled for unresolved repair work.'})
    if completion is None or not (
        completion.outcome == RepairCompletion.Outcome.NEEDS_FOLLOW_UP
        or completion.status == RepairCompletion.Status.REJECTED
    ):
        raise ValidationError({'completion': 'The latest completion must require follow-up or further work.'})
    if follow_up_at <= timezone.now():
        raise ValidationError({'follow_up_at': 'Choose a future follow-up time.'})
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A follow-up reason is required.'})
    membership = OrganizationMembership.objects.filter(
        user=assignee, organization_id=row.organization_id,
        organization__is_active=True, is_active=True,
        role__in=(
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.PROPERTY_MANAGER,
            OrganizationMembership.Role.CARETAKER,
            OrganizationMembership.Role.TECHNICIAN,
        ),
    ).first()
    if membership is None or not assignee.is_active:
        raise ValidationError({'assignee': 'The responsible person must be an active maintenance member of this organization.'})
    if membership.role == OrganizationMembership.Role.TECHNICIAN:
        if order.assignee_id != assignee.pk:
            raise ValidationError({'assignee': 'A technician follow-up must remain with the currently assigned technician.'})
        _validate_technician(row, assignee)
    if (
        row.follow_up_at == follow_up_at
        and row.follow_up_reason == reason.strip()
        and row.follow_up_assignee_id == assignee.pk
    ):
        return row
    before = {
        'follow_up_at': row.follow_up_at.isoformat() if row.follow_up_at else None,
        'follow_up_reason': row.follow_up_reason,
        'follow_up_assignee_id': row.follow_up_assignee_id,
    }
    row.follow_up_at = follow_up_at
    row.follow_up_reason = reason.strip()
    row.follow_up_assignee = assignee
    row.save(update_fields=('follow_up_at', 'follow_up_reason', 'follow_up_assignee', 'updated_at'))
    record_audit(
        action='maintenance.follow_up_scheduled', object_type='MaintenanceRequest', object_id=row.pk,
        actor=actor, organization=row.unit.building.property.organization,
        metadata={
            'before': before, 'follow_up_at': follow_up_at.isoformat(),
            'follow_up_assignee_id': assignee.pk, 'reason': reason.strip(),
        }, request=request,
    )
    notify_user(
        user=assignee, type='MAINTENANCE_FOLLOW_UP_SCHEDULED', title='Maintenance follow-up scheduled',
        body=row.title, organization=row.unit.building.property.organization,
        payload={'request_id': row.pk, 'follow_up_at': follow_up_at.isoformat()},
    )
    return row


@transaction.atomic
def cancel_request(maintenance_request, *, actor, reason, request=None):
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=maintenance_request.pk)
    if row.status not in (MaintenanceRequest.Status.OPEN, MaintenanceRequest.Status.IN_PROGRESS):
        raise ValidationError({'status': 'Only open or in-progress work can be cancelled.'})
    if not reason.strip():
        raise ValidationError({'reason': 'A cancellation reason is required.'})
    work_order = WorkOrder.objects.select_for_update().get(request=row)
    row.status = MaintenanceRequest.Status.CANCELLED
    row.save(update_fields=('status', 'updated_at'))
    work_order.status = WorkOrder.Status.CANCELLED
    work_order.save(update_fields=('status', 'updated_at'))
    issue = MaintenanceIssue.objects.select_for_update().filter(operational_request=row).first()
    if issue is not None:
        MaintenanceIssueUpdate.objects.create(
            issue=issue, author=actor, status=issue.status, note=f'Request cancelled: {reason.strip()}',
        )
    record_audit(action='maintenance.cancel', object_type='MaintenanceRequest', object_id=row.pk,
                 actor=actor, organization=row.unit.building.property.organization,
                 metadata={'reason': reason.strip(), 'work_order_id': work_order.pk}, request=request)
    return row


@transaction.atomic
def submit_quotation(work_order, *, actor, labour, materials, other, explanation, request=None):
    request_id = WorkOrder.objects.values_list('request_id', flat=True).get(pk=work_order.pk)
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=request_id)
    order = WorkOrder.objects.select_for_update().get(pk=work_order.pk)
    if row.status not in (MaintenanceRequest.Status.OPEN, MaintenanceRequest.Status.IN_PROGRESS):
        raise ValidationError({'status': 'Quotation cannot be submitted for a finished request.'})
    if row.requires_approval and order.status == WorkOrder.Status.IN_PROGRESS:
        raise ValidationError({'status': 'Work cannot proceed while a new approval is required.'})
    if min(labour, materials, other) < 0:
        raise ValidationError({'amounts': 'Quotation amounts cannot be negative.'})
    if order.quotations.filter(status=RepairQuotation.Status.PENDING).exists():
        raise ValidationError({'status': 'A quotation is already awaiting review.'})
    previous_quote = order.quotations.order_by('-created_at', '-pk').first()
    quote = RepairQuotation.objects.create(
        work_order=order, submitted_by=actor, labour_estimate_cents=labour,
        materials_estimate_cents=materials, other_estimate_cents=other,
        explanation=explanation.strip(), revision_of=previous_quote,
    )
    record_audit(action='maintenance.quote_submitted', object_type='RepairQuotation', object_id=quote.pk,
                 actor=actor, organization=row.unit.building.property.organization,
                 metadata={'work_order_id': order.pk, 'total_estimate_cents': quote.total_estimate_cents}, request=request)
    return quote


@transaction.atomic
def decide_quotation(quotation, *, actor, approve, notes='', request=None):
    order_id = RepairQuotation.objects.values_list('work_order_id', flat=True).get(pk=quotation.pk)
    request_id = WorkOrder.objects.values_list('request_id', flat=True).get(pk=order_id)
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=request_id)
    order = WorkOrder.objects.select_for_update().get(pk=order_id)
    quote = RepairQuotation.objects.select_for_update().get(pk=quotation.pk)
    if quote.status != RepairQuotation.Status.PENDING:
        raise ValidationError({'status': 'A decided quotation cannot be changed; submit a new revision.'})
    if quote.submitted_by_id == actor.pk:
        raise PermissionDenied('The quotation submitter cannot approve their own quotation.')
    if approve and row.requires_approval and order.status not in (WorkOrder.Status.PENDING, WorkOrder.Status.ASSIGNED):
        raise ValidationError({'status': 'Quotation approval is too late because work has started.'})
    quote.status = RepairQuotation.Status.APPROVED if approve else RepairQuotation.Status.REJECTED
    quote.reviewed_by = actor
    quote.decision_at = timezone.now()
    quote.decision_notes = notes.strip()
    quote.save(update_fields=('status', 'reviewed_by', 'decision_at', 'decision_notes'))
    record_audit(action='maintenance.quote_approved' if approve else 'maintenance.quote_rejected',
                 object_type='RepairQuotation', object_id=quote.pk, actor=actor,
                 organization=row.unit.building.property.organization,
                 metadata={'work_order_id': quote.work_order_id, 'total_estimate_cents': quote.total_estimate_cents},
                 request=request)
    return quote


@transaction.atomic
def submit_completion(work_order, *, actor, data, materials, request=None):
    request_id = WorkOrder.objects.values_list('request_id', flat=True).get(pk=work_order.pk)
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=request_id)
    order = WorkOrder.objects.select_for_update().get(pk=work_order.pk)
    if row.status != MaintenanceRequest.Status.IN_PROGRESS or order.status != WorkOrder.Status.IN_PROGRESS:
        raise ValidationError({'status': 'Only in-progress work can be submitted for verification.'})
    if order.assignee_id != actor.pk:
        raise PermissionDenied('Only the assigned technician can submit completion.')
    latest_quote = order.quotations.order_by('-created_at', '-pk').first()
    if row.requires_approval and not row.safety_override and (
        latest_quote is None or latest_quote.status != RepairQuotation.Status.APPROVED
    ):
        raise ValidationError({'detail': 'An approved quotation is required before completion.'})
    if min(data['labour_cost_cents'], data['materials_cost_cents'], data['other_cost_cents']) < 0:
        raise ValidationError({'costs': 'Actual costs cannot be negative.'})
    if data['outcome'] == RepairCompletion.Outcome.NEEDS_FOLLOW_UP and not data.get('follow_up_reason', '').strip():
        raise ValidationError({'follow_up_reason': 'A reason is required for follow-up work.'})
    completion = RepairCompletion.objects.create(
        work_order=order, submitted_by=actor,
        diagnosis=data['diagnosis'].strip(), failure_category=data['failure_category'].strip().upper(),
        resolution_summary=data['resolution_summary'].strip(), outcome=data['outcome'],
        labour_cost_cents=data['labour_cost_cents'], materials_cost_cents=data['materials_cost_cents'],
        other_cost_cents=data['other_cost_cents'],
        follow_up_required=data['outcome'] == RepairCompletion.Outcome.NEEDS_FOLLOW_UP,
        follow_up_reason=data.get('follow_up_reason', '').strip(),
    )
    for material in materials:
        RepairMaterialUsed.objects.create(completion=completion, **material)
    old_follow_up = None
    if row.follow_up_at is not None:
        old_follow_up = {
            'follow_up_at': row.follow_up_at.isoformat(),
            'follow_up_assignee_id': row.follow_up_assignee_id,
            'reason': row.follow_up_reason,
        }
        row.follow_up_at = None
        row.follow_up_reason = ''
        row.follow_up_assignee = None
    order.status = WorkOrder.Status.COMPLETED
    order.completed_at = completion.submitted_at
    order.notes = data['resolution_summary'].strip()
    order.save(update_fields=('status', 'completed_at', 'notes', 'updated_at'))
    row.status = MaintenanceRequest.Status.COMPLETED
    row.completed_at = completion.submitted_at
    row.save(update_fields=(
        'status', 'completed_at', 'follow_up_at', 'follow_up_reason', 'follow_up_assignee', 'updated_at',
    ))
    if old_follow_up:
        record_audit(
            action='maintenance.follow_up_completed', object_type='MaintenanceRequest', object_id=row.pk,
            actor=actor, organization=row.unit.building.property.organization,
            metadata={'completion_id': completion.pk, 'previous_schedule': old_follow_up}, request=request,
        )
    _sync_legacy_issue(row, actor=actor, status=MaintenanceIssue.Status.IN_PROGRESS,
                       note=f'Completion submitted for verification: {completion.pk}')
    record_audit(action='maintenance.completion_submitted', object_type='RepairCompletion', object_id=completion.pk,
                 actor=actor, organization=row.unit.building.property.organization,
                 metadata={'work_order_id': order.pk, 'outcome': completion.outcome,
                           'follow_up_required': completion.follow_up_required}, request=request)
    recipient = row.tenant.user if row.tenant_id else row.created_by
    notify_user(user=recipient, type='MAINTENANCE_UPDATED', title='Repair submitted for verification',
                body=row.title, organization=row.unit.building.property.organization,
                payload={'request_id': row.pk, 'status': row.status})
    return completion


@transaction.atomic
def verify_completion(completion, *, actor, approved, notes='', request=None):
    order_id = RepairCompletion.objects.values_list('work_order_id', flat=True).get(pk=completion.pk)
    request_id = WorkOrder.objects.values_list('request_id', flat=True).get(pk=order_id)
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=request_id)
    order = WorkOrder.objects.select_for_update().get(pk=order_id)
    item = RepairCompletion.objects.select_for_update().get(pk=completion.pk)
    if item.status != RepairCompletion.Status.SUBMITTED or row.status != MaintenanceRequest.Status.COMPLETED:
        raise ValidationError({'status': 'Only submitted completion can be verified.'})
    if item.submitted_by_id == actor.pk:
        raise PermissionDenied('The completing technician cannot verify their own work.')
    if approved and item.outcome == RepairCompletion.Outcome.NEEDS_FOLLOW_UP:
        raise ValidationError({'outcome': 'Follow-up work must be submitted and verified before closure.'})
    item.verification_notes = notes.strip()
    if approved:
        item.status = RepairCompletion.Status.VERIFIED
        item.verified_by = actor
        item.verified_at = timezone.now()
        row.status = MaintenanceRequest.Status.CLOSED
        row.closed_at = item.verified_at
        order.status = WorkOrder.Status.COMPLETED
        _sync_legacy_issue(row, actor=actor, status=MaintenanceIssue.Status.RESOLVED, note=notes or 'Repair verified.')
        action = 'maintenance.completion_verified'
    else:
        if not notes.strip():
            raise ValidationError({'notes': 'Explain what further work is required.'})
        item.status = RepairCompletion.Status.REJECTED
        row.status = MaintenanceRequest.Status.IN_PROGRESS
        row.completed_at = None
        order.status = WorkOrder.Status.IN_PROGRESS
        order.completed_at = None
        _sync_legacy_issue(row, actor=actor, status=MaintenanceIssue.Status.IN_PROGRESS, note=notes)
        action = 'maintenance.verification_rejected'
    item.save(update_fields=('status', 'verified_by', 'verified_at', 'verification_notes'))
    row.save(update_fields=('status', 'closed_at', 'completed_at', 'updated_at'))
    order.save(update_fields=('status', 'completed_at', 'updated_at'))
    record_audit(action=action, object_type='RepairCompletion', object_id=item.pk,
                 actor=actor, organization=row.unit.building.property.organization,
                 metadata={'work_order_id': order.pk}, request=request)
    recipient = row.tenant.user if row.tenant_id else row.created_by
    notify_user(user=recipient, type='MAINTENANCE_UPDATED',
                title='Repair verified' if approved else 'Further repair work requested', body=row.title,
                organization=row.unit.building.property.organization,
                payload={'request_id': row.pk, 'status': row.status})
    return item


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
