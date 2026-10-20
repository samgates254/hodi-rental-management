from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.leases.models import Lease
from apps.maintenance.models import (
    JobMaterialPurchase,
    JobMaterialReceipt,
    MaintenanceIssue,
    MaintenanceIssueUpdate,
    MaintenanceComment,
    MaintenanceRequest,
    RepairCompletion,
    RepairCompletionEvidence,
    RepairMaterialUsed,
    RepairQuotation,
    RepairQuotationLine,
    TurnoverAssessment,
    TurnoverChecklistItem,
    TechnicianProfile,
    WorkOrderAssignment,
    WorkOrder,
)
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Unit
from application.services.audit import record_audit
from application.services.notifications import notify_user
from engines.maintenance.priority.facade import score
from rental_os.algorithms.matching import Job, Technician
from rental_os.algorithms.priority import PriorityError
from rental_os.algorithms.matching import MatchingError
from rental_os.algorithms.money import MAX_MONEY_MINOR
from common.rental_dates import rental_business_date


OPEN_FOR_EDIT = {MaintenanceRequest.Status.OPEN, MaintenanceRequest.Status.IN_PROGRESS}
def quotation_line_total_cents(quantity, unit_price_cents):
    """Round nonnegative quantity × minor-unit price to cents using ROUND_HALF_UP."""
    try:
        with localcontext() as context:
            context.prec = 40
            amount = (Decimal(quantity) * Decimal(unit_price_cents)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError({'lines': 'A line contains an invalid quantity or price.'}) from error
    if amount < 0 or amount > MAX_MONEY_MINOR:
        raise ValidationError({'lines': 'A calculated line amount is outside the supported range.'})
    return int(amount)


def _itemized_totals(lines):
    subtotals = {'labour_estimate_cents': 0, 'materials_estimate_cents': 0, 'other_estimate_cents': 0}
    prepared = []
    for line in lines:
        quantity = line['quantity']
        price = line['unit_price_cents']
        if quantity <= 0 or price < 0:
            raise ValidationError({'lines': 'Quantities must be positive and prices cannot be negative.'})
        description = line['description'].strip()
        unit = line['unit'].strip()
        if not description or not unit:
            raise ValidationError({'lines': 'Every line needs a description and unit.'})
        total = quotation_line_total_cents(quantity, price)
        key = 'labour_estimate_cents' if line['category'] == RepairQuotationLine.Category.LABOUR else (
            'materials_estimate_cents' if line['category'] == RepairQuotationLine.Category.MATERIAL
            else 'other_estimate_cents'
        )
        subtotals[key] += total
        if subtotals[key] > MAX_MONEY_MINOR:
            raise ValidationError({'lines': 'A category subtotal is outside the supported range.'})
        prepared.append({**line, 'description': description, 'unit': unit, 'line_total_cents': total})
    if sum(subtotals.values()) > MAX_MONEY_MINOR:
        raise ValidationError({'lines': 'The quotation total is outside the supported range.'})
    return prepared, subtotals


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
        today = rental_business_date()
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
    if not actor.is_active:
        raise PermissionDenied('The assigned user is inactive.')
    membership = OrganizationMembership.objects.filter(
        user=actor,
        organization_id=row.organization_id,
        organization__is_active=True,
        is_active=True,
    ).first()
    allowed_start_roles = (
        OrganizationMembership.Role.OWNER,
        OrganizationMembership.Role.PROPERTY_MANAGER,
        OrganizationMembership.Role.CARETAKER,
        OrganizationMembership.Role.TECHNICIAN,
    )
    if membership is None or membership.role not in allowed_start_roles:
        raise PermissionDenied('An active authorized organization membership is required.')
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
def create_itemized_quotation(work_order, *, actor, lines, explanation, request=None):
    request_id = WorkOrder.objects.values_list('request_id', flat=True).get(pk=work_order.pk)
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=request_id)
    order = WorkOrder.objects.select_for_update().get(pk=work_order.pk)
    if row.status not in (MaintenanceRequest.Status.OPEN, MaintenanceRequest.Status.IN_PROGRESS):
        raise ValidationError({'status': 'Quotation cannot be created for a finished request.'})
    if row.requires_approval and order.status == WorkOrder.Status.IN_PROGRESS:
        raise ValidationError({'status': 'Work cannot proceed while a new approval is required.'})
    if order.quotations.filter(status__in=(RepairQuotation.Status.PENDING, RepairQuotation.Status.DRAFT)).exists():
        raise ValidationError({'status': 'A quotation draft or submission is already awaiting action.'})
    prepared, totals = _itemized_totals(lines)
    previous_quote = order.quotations.order_by('-created_at', '-pk').first()
    quote = RepairQuotation.objects.create(
        work_order=order, submitted_by=actor, revision_of=previous_quote,
        explanation=explanation.strip(), status=RepairQuotation.Status.DRAFT, **totals,
    )
    RepairQuotationLine.objects.bulk_create([
        RepairQuotationLine(quotation=quote, **line) for line in prepared
    ])
    record_audit(
        action='maintenance.quote_draft_created', object_type='RepairQuotation', object_id=quote.pk,
        actor=actor, organization=row.unit.building.property.organization,
        metadata={'work_order_id': order.pk, 'line_count': len(prepared),
                  'total_estimate_cents': quote.total_estimate_cents}, request=request,
    )
    return quote


@transaction.atomic
def replace_itemized_quotation_lines(quotation, *, actor, lines, explanation, request=None):
    order_id = RepairQuotation.objects.values_list('work_order_id', flat=True).get(pk=quotation.pk)
    request_id = WorkOrder.objects.values_list('request_id', flat=True).get(pk=order_id)
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=request_id)
    order = WorkOrder.objects.select_for_update().get(pk=order_id)
    quote = RepairQuotation.objects.select_for_update().get(pk=quotation.pk)
    if quote.status != RepairQuotation.Status.DRAFT:
        raise ValidationError({'status': 'Only an editable quotation draft can be changed.'})
    if quote.submitted_by_id != actor.pk:
        raise PermissionDenied('Only the quotation draft owner can edit it.')
    if row.status not in (MaintenanceRequest.Status.OPEN, MaintenanceRequest.Status.IN_PROGRESS):
        raise ValidationError({'status': 'Quotation cannot be edited for a finished request.'})
    prepared, totals = _itemized_totals(lines)
    quote.lines.all().delete()
    RepairQuotationLine.objects.bulk_create([
        RepairQuotationLine(quotation=quote, **line) for line in prepared
    ])
    quote.explanation = explanation.strip()
    for field, value in totals.items():
        setattr(quote, field, value)
    quote.save(update_fields=(*totals.keys(), 'explanation'))
    record_audit(
        action='maintenance.quote_draft_updated', object_type='RepairQuotation', object_id=quote.pk,
        actor=actor, organization=row.unit.building.property.organization,
        metadata={'work_order_id': order.pk, 'line_count': len(prepared),
                  'total_estimate_cents': quote.total_estimate_cents}, request=request,
    )
    return quote


@transaction.atomic
def submit_itemized_quotation(quotation, *, actor, request=None):
    order_id = RepairQuotation.objects.values_list('work_order_id', flat=True).get(pk=quotation.pk)
    request_id = WorkOrder.objects.values_list('request_id', flat=True).get(pk=order_id)
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=request_id)
    order = WorkOrder.objects.select_for_update().get(pk=order_id)
    quote = RepairQuotation.objects.select_for_update().get(pk=quotation.pk)
    if quote.status != RepairQuotation.Status.DRAFT:
        if quote.status == RepairQuotation.Status.PENDING:
            return quote
        raise ValidationError({'status': 'Only an editable quotation draft can be submitted.'})
    if quote.submitted_by_id != actor.pk:
        raise PermissionDenied('Only the quotation draft owner can submit it.')
    if not quote.lines.exists():
        raise ValidationError({'lines': 'Add at least one quotation line before submitting.'})
    if row.status not in (MaintenanceRequest.Status.OPEN, MaintenanceRequest.Status.IN_PROGRESS):
        raise ValidationError({'status': 'Quotation cannot be submitted for a finished request.'})
    if row.requires_approval and order.status == WorkOrder.Status.IN_PROGRESS:
        raise ValidationError({'status': 'Work cannot proceed while a new approval is required.'})
    if order.quotations.filter(status=RepairQuotation.Status.PENDING).exclude(pk=quote.pk).exists():
        raise ValidationError({'status': 'A quotation is already awaiting review.'})
    quote.status = RepairQuotation.Status.PENDING
    quote.save(update_fields=('status',))
    record_audit(
        action='maintenance.quote_submitted', object_type='RepairQuotation', object_id=quote.pk,
        actor=actor, organization=row.unit.building.property.organization,
        metadata={'work_order_id': order.pk, 'total_estimate_cents': quote.total_estimate_cents,
                  'itemized': True}, request=request,
    )
    return quote


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
    if order.quotations.filter(status__in=(RepairQuotation.Status.PENDING, RepairQuotation.Status.DRAFT)).exists():
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


PURCHASE_MANAGER_ROLES = (OrganizationMembership.Role.OWNER, OrganizationMembership.Role.PROPERTY_MANAGER)
RECEIPT_ROLES = (*PURCHASE_MANAGER_ROLES, OrganizationMembership.Role.CARETAKER)
TURNOVER_ROLES = (*PURCHASE_MANAGER_ROLES, OrganizationMembership.Role.CARETAKER)


def _has_organization_role(actor, organization_id, roles):
    return bool(actor.is_active and OrganizationMembership.objects.filter(
        user=actor, organization_id=organization_id, organization__is_active=True,
        is_active=True, role__in=roles,
    ).exists())


@transaction.atomic
def add_completion_evidence(completion, *, actor, category, caption, evidence_reference, request=None):
    request_id = RepairCompletion.objects.values_list('work_order__request_id', flat=True).get(pk=completion.pk)
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=request_id)
    item = RepairCompletion.objects.select_for_update().get(pk=completion.pk)
    if item.status != RepairCompletion.Status.SUBMITTED:
        raise ValidationError({'completion': 'Evidence can only be added while completion is awaiting verification.'})
    if item.work_order.request_id != row.pk or item.work_order.request.organization_id != row.organization_id:
        raise ValidationError({'completion': 'Completion and repair job relationships do not match.'})
    if item.submitted_by_id != actor.pk:
        raise PermissionDenied('Only the technician who submitted this completion may add evidence references.')
    evidence_reference = evidence_reference.strip()
    caption = caption.strip()
    prior = item.evidence.select_for_update().filter(evidence_reference=evidence_reference).first()
    if prior is not None:
        if prior.category != category or prior.caption != caption:
            raise ValidationError({'evidence_reference': 'This evidence reference is already linked with different details.'})
        return prior, False
    evidence = RepairCompletionEvidence.objects.create(
        completion=item, maintenance_request=row, organization_id=row.organization_id,
        category=category, caption=caption,
        evidence_reference=evidence_reference, recorded_by=actor,
    )
    record_audit(
        action='maintenance.completion_evidence_recorded', object_type='RepairCompletionEvidence',
        object_id=evidence.pk, actor=actor, organization=row.unit.building.property.organization,
        metadata={'completion_id': item.pk, 'request_id': row.pk, 'category': category}, request=request,
    )
    return evidence, True


def _assert_turnover_unit_is_vacant(unit):
    if unit.status not in (Unit.Status.AVAILABLE, Unit.Status.MAINTENANCE):
        raise ValidationError({'unit': 'Turnover readiness requires a vacant, rentable unit.'})
    if unit.leases.filter(status=Lease.Status.ACTIVE).exists():
        raise ValidationError({'unit': 'A unit with an active lease cannot undergo turnover readiness.'})


@transaction.atomic
def request_turnover_assessment(maintenance_request, *, actor, idempotency_key, request=None):
    unit_id = MaintenanceRequest.objects.values_list('unit_id', flat=True).get(pk=maintenance_request.pk)
    unit = Unit.objects.select_for_update().select_related('building__property__organization').get(pk=unit_id)
    row = MaintenanceRequest.objects.select_for_update().get(pk=maintenance_request.pk)
    if row.unit_id != unit.pk or row.organization_id != unit.organization_id:
        raise ValidationError({'maintenance_request': 'The repair job and unit must belong to the same organization.'})
    if not _has_organization_role(actor, row.organization_id, TURNOVER_ROLES):
        raise PermissionDenied('Only authorized property staff can request a turnover inspection.')
    if row.status == MaintenanceRequest.Status.CANCELLED:
        raise ValidationError({'maintenance_request': 'A cancelled repair job cannot be used for turnover readiness.'})
    _assert_turnover_unit_is_vacant(unit)
    organization = Organization.objects.select_for_update().get(pk=row.organization_id)
    prior_key = TurnoverAssessment.objects.select_for_update().filter(
        organization=organization, idempotency_key=idempotency_key,
    ).first()
    previous = TurnoverAssessment.objects.select_for_update().filter(
        maintenance_request=row,
    ).order_by('-requested_at', '-pk').first()
    if prior_key is not None:
        if prior_key.maintenance_request_id != row.pk:
            raise ValidationError({'idempotency_key': 'This request key is already used for another job.'})
        return prior_key, False
    if previous is not None and previous.status == TurnoverAssessment.Status.REQUESTED:
        raise ValidationError({'status': 'Complete or cancel the current turnover inspection before requesting another.'})
    assessment = TurnoverAssessment.objects.create(
        organization=organization, property=unit.building.property, building=unit.building,
        unit=unit, maintenance_request=row, revision_of=previous, requested_by=actor,
        idempotency_key=idempotency_key,
    )
    record_audit(
        action='maintenance.turnover_inspection_requested', object_type='TurnoverAssessment',
        object_id=assessment.pk, actor=actor, organization=organization,
        metadata={'request_id': row.pk, 'unit_id': unit.pk, 'revision_of_id': previous.pk if previous else None},
        request=request,
    )
    return assessment, True


@transaction.atomic
def assess_turnover_readiness(
    assessment, *, actor, checklist_items, ready, outstanding_issues='', request=None,
):
    unit_id = TurnoverAssessment.objects.values_list('unit_id', flat=True).get(pk=assessment.pk)
    unit = Unit.objects.select_for_update().select_related('building__property__organization').get(pk=unit_id)
    item = TurnoverAssessment.objects.select_for_update(of=('self',)).select_related(
        'maintenance_request__work_order', 'organization',
    ).get(pk=assessment.pk)
    if (item.unit_id != unit.pk or item.maintenance_request.unit_id != unit.pk
            or item.building_id != unit.building_id or item.property_id != unit.building.property_id
            or item.organization_id != unit.organization_id
            or item.maintenance_request.organization_id != item.organization_id):
        raise ValidationError({'unit': 'Assessment, repair job and unit relationships do not match.'})
    if not _has_organization_role(actor, item.organization_id, TURNOVER_ROLES):
        raise PermissionDenied('Only authorized property staff can assess turnover readiness.')
    if ready and not _has_organization_role(actor, item.organization_id, PURCHASE_MANAGER_ROLES):
        raise PermissionDenied('Only an owner or property manager can confirm the unit ready for its next tenancy.')
    issues = outstanding_issues.strip()
    normalized_items = sorted(checklist_items, key=lambda value: value['item_key'])
    existing_items = list(item.checklist_items.order_by('item_key').values(
        'item_key', 'label', 'passed', 'notes',
    ))
    if item.status != TurnoverAssessment.Status.REQUESTED:
        same_decision = (
            item.status == (TurnoverAssessment.Status.READY if ready else TurnoverAssessment.Status.FAILED)
            and item.outstanding_issues == issues
            and existing_items == normalized_items
        )
        if same_decision:
            return item, False
        raise ValidationError({'status': 'A decided inspection is immutable; create a reassessment instead.'})
    if not _has_organization_role(actor, item.organization_id, TURNOVER_ROLES):
        raise PermissionDenied('Only authorized property staff can assess turnover readiness.')
    if not normalized_items:
        raise ValidationError({'checklist_items': 'Record at least one checklist result.'})
    if ready:
        _assert_turnover_unit_is_vacant(unit)
        if issues or any(not checklist['passed'] for checklist in normalized_items):
            raise ValidationError({'ready': 'A unit cannot pass with outstanding issues or failed checklist items.'})
        completion = item.maintenance_request.work_order.completions.order_by('-submitted_at', '-pk').first()
        if (item.maintenance_request.status != MaintenanceRequest.Status.CLOSED or completion is None
                or completion.status != RepairCompletion.Status.VERIFIED):
            raise ValidationError({'maintenance_request': 'The associated repair must be verified before readiness can pass.'})
        decision_status = TurnoverAssessment.Status.READY
    else:
        if not issues and all(checklist['passed'] for checklist in normalized_items):
            raise ValidationError({'outstanding_issues': 'Explain why the inspection did not pass or identify a failed checklist item.'})
        decision_status = TurnoverAssessment.Status.FAILED
    TurnoverChecklistItem.objects.bulk_create([
        TurnoverChecklistItem(assessment=item, **checklist) for checklist in normalized_items
    ])
    item.status = decision_status
    item.outstanding_issues = issues
    item.assessed_by = actor
    item.assessed_at = timezone.now()
    item.save(update_fields=('status', 'outstanding_issues', 'assessed_by', 'assessed_at'))
    record_audit(
        action='maintenance.turnover_readiness_recorded', object_type='TurnoverAssessment',
        object_id=item.pk, actor=actor, organization=item.organization,
        metadata={'request_id': item.maintenance_request_id, 'unit_id': unit.pk,
                  'status': item.status, 'checklist_count': len(normalized_items)}, request=request,
    )
    return item, True


def _purchase_request_matches(purchase, *, maintenance_request):
    return (
        purchase.maintenance_request_id == maintenance_request.pk
        and purchase.organization_id == maintenance_request.organization_id
        and purchase.quotation.work_order.request_id == maintenance_request.pk
        and purchase.quotation_line.quotation_id == purchase.quotation_id
    )


@transaction.atomic
def record_material_purchase(
    maintenance_request, *, actor, quotation_id, quotation_line_id, supplier_name,
    supplier_reference='', supplier_profile=None, quantity, unit_price_cents, purchase_date,
    idempotency_key, overrun_reason='', request=None,
):
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=maintenance_request.pk)
    organization = Organization.objects.select_for_update().get(pk=row.organization_id)
    if supplier_profile is not None and (supplier_profile.organization_id != organization.pk or not supplier_profile.is_active):
        raise ValidationError({'supplier_profile': 'Choose an active supplier profile belonging to this organization.'})
    if not _has_organization_role(actor, organization.pk, PURCHASE_MANAGER_ROLES):
        raise PermissionDenied('Only an organization owner or property manager can record a material purchase.')
    if row.status not in (MaintenanceRequest.Status.OPEN, MaintenanceRequest.Status.IN_PROGRESS):
        raise ValidationError({'status': 'Purchases can only be recorded for open or in-progress repair jobs.'})
    prior = JobMaterialPurchase.objects.select_for_update().filter(
        organization=organization, idempotency_key=idempotency_key,
    ).first()
    if prior is not None:
        same_request = (
            prior.maintenance_request_id == row.pk
            and prior.quotation_id == quotation_id
            and prior.quotation_line_id == quotation_line_id
            and prior.supplier_name == supplier_name.strip()
            and prior.supplier_profile_id == getattr(supplier_profile, 'pk', None)
            and prior.supplier_reference == supplier_reference.strip()
            and prior.quantity == quantity
            and prior.unit_price_cents == unit_price_cents
            and prior.purchase_date == purchase_date
            and prior.overrun_reason == overrun_reason.strip()
        )
        if not same_request:
            raise ValidationError({'idempotency_key': 'This request key was already used for different purchase details.'})
        return prior, False

    order = WorkOrder.objects.select_for_update().get(request_id=row.pk)
    quotation = order.quotations.select_for_update().filter(pk=quotation_id).first()
    latest_quotation = order.quotations.order_by('-created_at', '-pk').first()
    if quotation is None or quotation.status != RepairQuotation.Status.APPROVED or latest_quotation is None or latest_quotation.pk != quotation.pk:
        raise ValidationError({'quotation': 'Purchases require the current approved quotation revision.'})
    line = RepairQuotationLine.objects.select_for_update().filter(
        pk=quotation_line_id, quotation=quotation, category=RepairQuotationLine.Category.MATERIAL,
    ).first()
    if line is None:
        raise ValidationError({'quotation_line': 'Choose a material line from the current approved quotation.'})
    if quantity <= 0 or unit_price_cents < 0:
        raise ValidationError({'quantity': 'Quantity must be positive and price cannot be negative.'})
    purchased_quantity = sum(order_item.quantity for order_item in JobMaterialPurchase.objects.filter(quotation_line=line))
    if purchased_quantity + quantity > line.quantity:
        raise ValidationError({'quantity': 'Purchase quantity exceeds the approved material requirement.'})
    amount = quotation_line_total_cents(quantity, unit_price_cents)
    recorded_material_spend = sum(
        item.purchase_total_cents for item in JobMaterialPurchase.objects.filter(quotation=quotation)
    )
    if recorded_material_spend + amount > MAX_MONEY_MINOR:
        raise ValidationError({'quantity': 'The recorded material spend exceeds the supported monetary range.'})
    exceeds_budget = recorded_material_spend + amount > quotation.materials_estimate_cents
    if exceeds_budget and not overrun_reason.strip():
        raise ValidationError({'overrun_reason': 'An owner or property manager must explicitly authorize the material budget overrun with a reason.'})
    if overrun_reason.strip() and not exceeds_budget:
        raise ValidationError({'overrun_reason': 'An overrun reason is only valid when the approved material budget would be exceeded.'})

    purchase = JobMaterialPurchase.objects.create(
        organization=organization, maintenance_request=row, quotation=quotation, quotation_line=line,
        supplier_name=supplier_name.strip(), supplier_reference=supplier_reference.strip(),
        supplier_profile=supplier_profile,
        description=line.description, quantity=quantity, unit=line.unit,
        unit_price_cents=unit_price_cents, purchase_total_cents=amount, purchase_date=purchase_date,
        idempotency_key=idempotency_key, created_by=actor,
        overrun_reason=overrun_reason.strip() if exceeds_budget else '',
        overrun_authorized_by=actor if exceeds_budget else None,
        overrun_authorized_at=timezone.now() if exceeds_budget else None,
    )
    record_audit(
        action='maintenance.material_purchase_recorded', object_type='JobMaterialPurchase', object_id=purchase.pk,
        actor=actor, organization=organization,
        metadata={'request_id': row.pk, 'quotation_id': quotation.pk, 'quotation_line_id': line.pk,
                  'quantity': str(quantity), 'purchase_total_cents': amount,
                  'overrun_authorized': exceeds_budget}, request=request,
    )
    return purchase, True


@transaction.atomic
def acknowledge_material_receipt(
    purchase, *, actor, quantity, evidence_reference, idempotency_key, notes='', request=None,
):
    request_id = JobMaterialPurchase.objects.values_list('maintenance_request_id', flat=True).get(pk=purchase.pk)
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=request_id)
    item = JobMaterialPurchase.objects.select_for_update().select_related('quotation', 'quotation_line').get(pk=purchase.pk)
    if not _purchase_request_matches(item, maintenance_request=row):
        raise ValidationError({'purchase': 'Purchase does not belong to this organization and repair job.'})
    if not _has_organization_role(actor, row.organization_id, RECEIPT_ROLES):
        raise PermissionDenied('Only owners, property managers or caretakers can acknowledge material receipt.')
    prior = item.receipts.select_for_update().filter(idempotency_key=idempotency_key).first()
    if prior is not None:
        if (prior.quantity != quantity or prior.evidence_reference != evidence_reference.strip()
                or prior.notes != notes.strip()):
            raise ValidationError({'idempotency_key': 'This receipt key was already used for different receipt details.'})
        return prior, item, False
    if item.created_by_id == actor.pk:
        raise PermissionDenied('The purchase recorder cannot acknowledge receipt of their own purchase.')
    if item.status == JobMaterialPurchase.Status.RECEIVED:
        raise ValidationError({'status': 'This purchase is already fully received.'})
    if quantity <= 0 or not evidence_reference.strip():
        raise ValidationError({'evidence_reference': 'A positive received quantity and evidence reference are required.'})
    received_quantity = sum(receipt.quantity for receipt in item.receipts.all())
    if received_quantity + quantity > item.quantity:
        raise ValidationError({'quantity': 'Received quantity cannot exceed the recorded purchase quantity.'})
    receipt = JobMaterialReceipt.objects.create(
        purchase=item, quantity=quantity, evidence_reference=evidence_reference.strip(),
        notes=notes.strip(), idempotency_key=idempotency_key, acknowledged_by=actor,
    )
    new_total_received = received_quantity + quantity
    item.status = (
        JobMaterialPurchase.Status.RECEIVED if new_total_received == item.quantity
        else JobMaterialPurchase.Status.PARTIALLY_RECEIVED
    )
    item.save(update_fields=('status',))
    record_audit(
        action='maintenance.material_receipt_acknowledged', object_type='JobMaterialReceipt', object_id=receipt.pk,
        actor=actor, organization=row.unit.building.property.organization,
        metadata={'purchase_id': item.pk, 'quantity': str(quantity), 'receipt_status': item.status}, request=request,
    )
    return receipt, item, True


def job_cost_summary(maintenance_request):
    order = WorkOrder.objects.filter(request=maintenance_request).first()
    latest_quotation = order.quotations.order_by('-created_at', '-pk').first() if order else None
    approved_quotation = order.quotations.filter(status=RepairQuotation.Status.APPROVED).order_by('-created_at', '-pk').first() if order else None
    completion = order.completions.order_by('-submitted_at', '-pk').first() if order else None
    purchases = list(JobMaterialPurchase.objects.filter(maintenance_request=maintenance_request))
    purchase_total = sum(item.purchase_total_cents for item in purchases)
    labour_actual = completion.labour_cost_cents if completion else 0
    other_actual = completion.other_cost_cents if completion else 0
    reported_material_actual = completion.materials_cost_cents if completion else 0
    recorded_cost = purchase_total + labour_actual + other_actual
    approved_total = approved_quotation.total_estimate_cents if approved_quotation else None
    linked_uses = list(RepairMaterialUsed.objects.filter(
        completion=completion, purchase__isnull=False,
    )) if completion else []
    unlinked_use_exists = RepairMaterialUsed.objects.filter(completion=completion, purchase__isnull=True).exists() if completion else False
    linked_consumed_value = sum(
        quotation_line_total_cents(use.quantity, use.unit_cost_cents) for use in linked_uses
    )
    materials_reconciled = not unlinked_use_exists and linked_consumed_value == reported_material_actual
    provisional = bool(
        completion is None or completion.status != RepairCompletion.Status.VERIFIED
        or not materials_reconciled
        or approved_quotation is None
        or (approved_quotation is not None and latest_quotation is not None and latest_quotation.pk != approved_quotation.pk)
    )
    return {
        'latest_quotation_status': latest_quotation.status if latest_quotation else None,
        'approved_quotation_id': approved_quotation.pk if approved_quotation else None,
        'approved_quotation_is_current': bool(approved_quotation and latest_quotation and approved_quotation.pk == latest_quotation.pk),
        'approved_total_cents': approved_total,
        'approved_material_budget_cents': approved_quotation.materials_estimate_cents if approved_quotation else None,
        'recorded_purchase_total_cents': purchase_total,
        'received_purchase_count': sum(item.status == JobMaterialPurchase.Status.RECEIVED for item in purchases),
        'unreceived_purchase_count': sum(item.status != JobMaterialPurchase.Status.RECEIVED for item in purchases),
        'recorded_labour_actual_cents': labour_actual,
        'reported_material_consumption_cost_cents': reported_material_actual,
        'recorded_other_actual_cents': other_actual,
        'recorded_job_cost_cents': recorded_cost,
        'variance_cents': recorded_cost - approved_total if approved_total is not None else None,
        'over_budget': bool(approved_total is not None and recorded_cost > approved_total),
        'cost_summary_status': 'PROVISIONAL' if provisional else 'FINAL_RECORDED',
        'materials_reconciled': materials_reconciled,
        'supplier_payment_status': 'NOT_TRACKED',
    }


@transaction.atomic
def submit_completion(work_order, *, actor, data, materials, request=None):
    request_id = WorkOrder.objects.values_list('request_id', flat=True).get(pk=work_order.pk)
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=request_id)
    order = WorkOrder.objects.select_for_update().get(pk=work_order.pk)
    if row.status != MaintenanceRequest.Status.IN_PROGRESS or order.status != WorkOrder.Status.IN_PROGRESS:
        raise ValidationError({'status': 'Only in-progress work can be submitted for verification.'})
    if order.assignee_id != actor.pk:
        raise PermissionDenied('Only the assigned technician can submit completion.')
    if not actor.is_active:
        raise PermissionDenied('The assigned user is inactive.')
    membership = OrganizationMembership.objects.filter(
        user=actor,
        organization_id=row.organization_id,
        organization__is_active=True,
        is_active=True,
    ).first()
    allowed_completion_roles = (
        OrganizationMembership.Role.OWNER,
        OrganizationMembership.Role.PROPERTY_MANAGER,
        OrganizationMembership.Role.CARETAKER,
        OrganizationMembership.Role.TECHNICIAN,
    )
    if membership is None or membership.role not in allowed_completion_roles:
        raise PermissionDenied('An active authorized organization membership is required.')
    if membership.role == OrganizationMembership.Role.TECHNICIAN:
        _validate_technician(row, actor)
    latest_quote = order.quotations.order_by('-created_at', '-pk').first()
    if row.requires_approval and not row.safety_override and (
        latest_quote is None or latest_quote.status != RepairQuotation.Status.APPROVED
    ):
        raise ValidationError({'detail': 'An approved quotation is required before completion.'})
    prepared_materials = []
    pending_consumption = {}
    for source in materials:
        material = dict(source)
        purchase_id = material.pop('purchase_id', None)
        if purchase_id is not None:
            purchase = JobMaterialPurchase.objects.select_for_update().filter(pk=purchase_id).first()
            if purchase is None or not _purchase_request_matches(purchase, maintenance_request=row):
                raise ValidationError({'materials': 'A linked purchase must belong to this repair job and organization.'})
            received = sum((receipt.quantity for receipt in purchase.receipts.all()), Decimal('0'))
            previously_used = sum(use.quantity for use in RepairMaterialUsed.objects.filter(purchase=purchase))
            already_in_submission = pending_consumption.get(purchase.pk, Decimal('0'))
            if previously_used + already_in_submission + material['quantity'] > received:
                raise ValidationError({'materials': 'Material use cannot exceed the quantity received for its purchase.'})
            pending_consumption[purchase.pk] = already_in_submission + material['quantity']
            material.update(
                purchase=purchase,
                description=purchase.description,
                unit=purchase.unit,
                unit_cost_cents=purchase.unit_price_cents,
            )
        prepared_materials.append(material)
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
    for material in prepared_materials:
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
def verify_completion(
    completion, *, actor, approved, notes='', authorize_cost_overrun=False,
    cost_overrun_reason='', request=None,
):
    order_id = RepairCompletion.objects.values_list('work_order_id', flat=True).get(pk=completion.pk)
    request_id = WorkOrder.objects.values_list('request_id', flat=True).get(pk=order_id)
    row = MaintenanceRequest.objects.select_for_update().select_related('unit__building__property').get(pk=request_id)
    order = WorkOrder.objects.select_for_update().get(pk=order_id)
    item = RepairCompletion.objects.select_for_update().get(pk=completion.pk)
    if not _has_organization_role(
        actor,
        row.organization_id,
        (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.PROPERTY_MANAGER,
            OrganizationMembership.Role.CARETAKER,
        ),
    ):
        raise PermissionDenied('Only authorized maintenance staff can verify repairs.')
    if item.status != RepairCompletion.Status.SUBMITTED or row.status != MaintenanceRequest.Status.COMPLETED:
        raise ValidationError({'status': 'Only submitted completion can be verified.'})
    if item.submitted_by_id == actor.pk:
        raise PermissionDenied('The completing technician cannot verify their own work.')
    if approved and item.outcome == RepairCompletion.Outcome.NEEDS_FOLLOW_UP:
        raise ValidationError({'outcome': 'Follow-up work must be submitted and verified before closure.'})
    item.verification_notes = notes.strip()
    cost_summary = job_cost_summary(row)
    if approved and cost_summary['over_budget']:
        if not authorize_cost_overrun or not cost_overrun_reason.strip():
            raise ValidationError({
                'cost_overrun_reason': 'The recorded job cost exceeds the approved quotation; an owner or property manager must explicitly authorize the variance with a reason.',
            })
        if not _has_organization_role(actor, row.organization_id, PURCHASE_MANAGER_ROLES):
            raise PermissionDenied('Only an organization owner or property manager can authorize a cost overrun.')
        item.cost_overrun_reason = cost_overrun_reason.strip()
        item.cost_overrun_authorized_by = actor
        item.cost_overrun_authorized_at = timezone.now()
    elif authorize_cost_overrun or cost_overrun_reason.strip():
        raise ValidationError({'cost_overrun_reason': 'A cost overrun authorization is only valid when the recorded job cost exceeds the approved quotation.'})
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
    item.save(update_fields=(
        'status', 'verified_by', 'verified_at', 'verification_notes',
        'cost_overrun_reason', 'cost_overrun_authorized_by', 'cost_overrun_authorized_at',
    ))
    row.save(update_fields=('status', 'closed_at', 'completed_at', 'updated_at'))
    order.save(update_fields=('status', 'completed_at', 'updated_at'))
    record_audit(action=action, object_type='RepairCompletion', object_id=item.pk,
                 actor=actor, organization=row.unit.building.property.organization,
                 metadata={'work_order_id': order.pk, 'recorded_job_cost_cents': cost_summary['recorded_job_cost_cents'],
                           'variance_cents': cost_summary['variance_cents'],
                           'cost_overrun_authorized': bool(item.cost_overrun_authorized_at)}, request=request)
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


MAX_MATCH_PREVIEW_JOBS = 50
MAX_MATCH_PREVIEW_TECHNICIANS = 50


def preview_matches(*, organization, jobs):
    if not isinstance(jobs, list) or len(jobs) > MAX_MATCH_PREVIEW_JOBS:
        raise ValidationError({
            'jobs': f'Provide no more than {MAX_MATCH_PREVIEW_JOBS} jobs per preview.',
        })
    memberships = OrganizationMembership.objects.filter(
        organization=organization,
        role=OrganizationMembership.Role.TECHNICIAN,
        is_active=True,
        organization__is_active=True,
    ).select_related('user', 'user__account_profile', 'user__technician_profile')[:MAX_MATCH_PREVIEW_TECHNICIANS + 1]
    memberships = list(memberships)
    if len(memberships) > MAX_MATCH_PREVIEW_TECHNICIANS:
        raise ValidationError({
            'technicians': (
                f'Matching previews support no more than '
                f'{MAX_MATCH_PREVIEW_TECHNICIANS} active technicians.'
            ),
        })
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
