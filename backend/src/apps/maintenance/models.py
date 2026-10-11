from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.properties.models import Unit
from apps.tenants.models import Tenant


class MaintenanceIssue(models.Model):
	class Priority(models.TextChoices):
		LOW = 'LOW', 'Low'
		NORMAL = 'NORMAL', 'Normal'
		HIGH = 'HIGH', 'High'
		URGENT = 'URGENT', 'Urgent'

	class Status(models.TextChoices):
		OPEN = 'OPEN', 'Open'
		IN_PROGRESS = 'IN_PROGRESS', 'In progress'
		RESOLVED = 'RESOLVED', 'Resolved'

	tenant = models.ForeignKey(
		Tenant,
		on_delete=models.PROTECT,
		related_name='maintenance_issues',
	)
	unit = models.ForeignKey(
		Unit,
		on_delete=models.PROTECT,
		related_name='maintenance_issues',
	)
	title = models.CharField(max_length=200)
	category = models.CharField(max_length=50)
	priority = models.CharField(
		max_length=20,
		choices=Priority.choices,
		default=Priority.NORMAL,
	)
	description = models.TextField()
	status = models.CharField(
		max_length=20,
		choices=Status.choices,
		default=Status.OPEN,
	)
	resolved_at = models.DateTimeField(null=True, blank=True)
	operational_request = models.OneToOneField(
		'MaintenanceRequest', null=True, blank=True, on_delete=models.PROTECT,
		related_name='legacy_issue',
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('-created_at',)
		indexes = [
			models.Index(fields=('unit', 'status'), name='maint_issue_unit_status_idx'),
		]

	@property
	def organization_id(self):
		return self.tenant.organization_id

	def clean(self):
		super().clean()
		if self.tenant_id and self.unit_id:
			if self.tenant.organization_id != self.unit.organization_id:
				raise ValidationError('Tenant and unit must belong to the same organization.')

	def __str__(self):
		return self.title


class MaintenanceIssueAttachment(models.Model):
	class MediaType(models.TextChoices):
		IMAGE = 'IMAGE', 'Image'
		VIDEO = 'VIDEO', 'Video'

	issue = models.ForeignKey(
		MaintenanceIssue,
		on_delete=models.CASCADE,
		related_name='attachments',
	)
	file = models.FileField(upload_to='maintenance/issues/%Y/%m/')
	file_name = models.CharField(max_length=255)
	content_type = models.CharField(max_length=100)
	media_type = models.CharField(max_length=10, choices=MediaType.choices)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('created_at', 'pk')

	def __str__(self):
		return self.file_name


class MaintenanceIssueUpdate(models.Model):
	issue = models.ForeignKey(
		MaintenanceIssue,
		on_delete=models.CASCADE,
		related_name='updates',
	)
	author = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='maintenance_issue_updates',
	)
	status = models.CharField(
		max_length=20,
		choices=MaintenanceIssue.Status.choices,
		null=True,
		blank=True,
	)
	note = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('created_at', 'pk')

	def __str__(self):
		return f'{self.issue}: {self.status or "note"}'


class MaintenanceRequest(models.Model):
	class Status(models.TextChoices):
		OPEN = 'OPEN', 'Open'
		IN_PROGRESS = 'IN_PROGRESS', 'In progress'
		COMPLETED = 'COMPLETED', 'Completed'
		CLOSED = 'CLOSED', 'Closed'
		CANCELLED = 'CANCELLED', 'Cancelled'

	unit = models.ForeignKey(
		Unit,
		on_delete=models.PROTECT,
		related_name='maintenance_requests',
	)
	category = models.CharField(max_length=50, default='OTHER')
	tenant = models.ForeignKey(
		Tenant,
		on_delete=models.PROTECT,
		null=True,
		blank=True,
		related_name='maintenance_requests',
	)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='maintenance_requests',
	)
	title = models.CharField(max_length=200)
	description = models.TextField()
	hazard = models.PositiveSmallIntegerField()
	vulnerability = models.PositiveSmallIntegerField(default=1)
	status = models.CharField(
		max_length=20,
		choices=Status.choices,
		default=Status.OPEN,
	)
	priority_class = models.PositiveSmallIntegerField()
	score_millis = models.PositiveIntegerField()
	emergency_override = models.BooleanField(default=False)
	safety_override = models.BooleanField(default=False)
	safety_override_reason = models.CharField(max_length=500, blank=True)
	safety_override_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
		related_name='maintenance_safety_overrides',
	)
	triage_notes = models.TextField(blank=True)
	triaged_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
		related_name='triaged_maintenance_requests',
	)
	triaged_at = models.DateTimeField(null=True, blank=True)
	requires_approval = models.BooleanField(default=False)
	follow_up_at = models.DateTimeField(null=True, blank=True)
	follow_up_reason = models.CharField(max_length=500, blank=True)
	follow_up_assignee = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
		related_name='maintenance_follow_ups',
	)
	completed_at = models.DateTimeField(null=True, blank=True)
	closed_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('priority_class', '-created_at')
		indexes = [
			models.Index(fields=('status',), name='maint_request_status_idx'),
		]

	@property
	def organization_id(self):
		return self.unit.organization_id

	def clean(self):
		super().clean()
		if self.hazard < 1 or self.hazard > 5:
			raise ValidationError('Hazard must be between 1 and 5.')
		if self.vulnerability < 1 or self.vulnerability > 5:
			raise ValidationError('Vulnerability must be between 1 and 5.')
		if self.tenant_id and self.unit_id:
			if self.tenant.organization_id != self.unit.organization_id:
				raise ValidationError('Tenant and unit must belong to the same organization.')

	def __str__(self):
		return self.title


class WorkOrder(models.Model):
	class Status(models.TextChoices):
		PENDING = 'PENDING', 'Pending'
		ASSIGNED = 'ASSIGNED', 'Assigned'
		IN_PROGRESS = 'IN_PROGRESS', 'In progress'
		COMPLETED = 'COMPLETED', 'Completed'
		CANCELLED = 'CANCELLED', 'Cancelled'

	request = models.OneToOneField(
		MaintenanceRequest,
		on_delete=models.CASCADE,
		related_name='work_order',
	)
	assignee = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		null=True,
		blank=True,
		related_name='assigned_work_orders',
	)
	status = models.CharField(
		max_length=20,
		choices=Status.choices,
		default=Status.PENDING,
	)
	assigned_at = models.DateTimeField(null=True, blank=True)
	completed_at = models.DateTimeField(null=True, blank=True)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('-created_at',)

	@property
	def organization_id(self):
		return self.request.organization_id

	def __str__(self):
		return f'Work order {self.pk}'


class WorkOrderAssignment(models.Model):
	class Status(models.TextChoices):
		NOT_REQUIRED = 'NOT_REQUIRED', 'No technician response required'
		PENDING = 'PENDING', 'Awaiting technician response'
		ACCEPTED = 'ACCEPTED', 'Accepted'
		DECLINED = 'DECLINED', 'Declined'

	work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name='assignments')
	previous_assignee = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
		related_name='maintenance_assignments_from',
	)
	new_assignee = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
		related_name='maintenance_assignments_to',
	)
	actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='maintenance_assignment_actions')
	notes = models.TextField(blank=True)
	status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
	responded_at = models.DateTimeField(null=True, blank=True)
	decline_reason = models.CharField(max_length=500, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('created_at', 'pk')


class RepairQuotation(models.Model):
	class Status(models.TextChoices):
		PENDING = 'PENDING', 'Pending'
		APPROVED = 'APPROVED', 'Approved'
		REJECTED = 'REJECTED', 'Rejected'

	work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name='quotations')
	revision_of = models.ForeignKey(
		'self', on_delete=models.PROTECT, null=True, blank=True, related_name='revisions',
	)
	submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='repair_quotations')
	labour_estimate_cents = models.PositiveBigIntegerField(default=0)
	materials_estimate_cents = models.PositiveBigIntegerField(default=0)
	other_estimate_cents = models.PositiveBigIntegerField(default=0)
	explanation = models.TextField()
	status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
	reviewed_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
		related_name='reviewed_repair_quotations',
	)
	decision_at = models.DateTimeField(null=True, blank=True)
	decision_notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	@property
	def total_estimate_cents(self):
		return self.labour_estimate_cents + self.materials_estimate_cents + self.other_estimate_cents

	class Meta:
		ordering = ('-created_at', '-pk')
		constraints = [
			models.CheckConstraint(condition=models.Q(labour_estimate_cents__gte=0), name='repair_quote_labour_nonnegative'),
			models.CheckConstraint(condition=models.Q(materials_estimate_cents__gte=0), name='repair_quote_materials_nonnegative'),
			models.CheckConstraint(condition=models.Q(other_estimate_cents__gte=0), name='repair_quote_other_nonnegative'),
		]


class RepairCompletion(models.Model):
	class Status(models.TextChoices):
		SUBMITTED = 'SUBMITTED', 'Submitted'
		REJECTED = 'REJECTED', 'Rejected for further work'
		VERIFIED = 'VERIFIED', 'Verified'

	class Outcome(models.TextChoices):
		FIXED = 'FIXED', 'Fixed'
		PARTIALLY_FIXED = 'PARTIALLY_FIXED', 'Partially fixed'
		REPLACED = 'REPLACED', 'Replaced'
		NO_FAULT_FOUND = 'NO_FAULT_FOUND', 'No fault found'
		NEEDS_FOLLOW_UP = 'NEEDS_FOLLOW_UP', 'Needs follow-up'

	work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name='completions')
	diagnosis = models.TextField()
	failure_category = models.CharField(max_length=50)
	resolution_summary = models.TextField()
	outcome = models.CharField(max_length=24, choices=Outcome.choices)
	labour_cost_cents = models.PositiveBigIntegerField(default=0)
	materials_cost_cents = models.PositiveBigIntegerField(default=0)
	other_cost_cents = models.PositiveBigIntegerField(default=0)
	submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='repair_completions_submitted')
	submitted_at = models.DateTimeField(auto_now_add=True)
	status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUBMITTED)
	verified_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
		related_name='repair_completions_verified',
	)
	verified_at = models.DateTimeField(null=True, blank=True)
	verification_notes = models.TextField(blank=True)
	follow_up_required = models.BooleanField(default=False)
	follow_up_reason = models.CharField(max_length=500, blank=True)

	class Meta:
		ordering = ('-submitted_at', '-pk')
		constraints = [
			models.CheckConstraint(condition=models.Q(labour_cost_cents__gte=0), name='repair_completion_labour_nonnegative'),
			models.CheckConstraint(condition=models.Q(materials_cost_cents__gte=0), name='repair_completion_materials_nonnegative'),
			models.CheckConstraint(condition=models.Q(other_cost_cents__gte=0), name='repair_completion_other_nonnegative'),
		]


class RepairMaterialUsed(models.Model):
	completion = models.ForeignKey(RepairCompletion, on_delete=models.PROTECT, related_name='materials')
	description = models.CharField(max_length=200)
	quantity = models.DecimalField(max_digits=12, decimal_places=3)
	unit = models.CharField(max_length=30)
	unit_cost_cents = models.PositiveBigIntegerField(default=0)

	class Meta:
		constraints = [
			models.CheckConstraint(condition=models.Q(quantity__gt=0), name='repair_material_quantity_positive'),
			models.CheckConstraint(condition=models.Q(unit_cost_cents__gte=0), name='repair_material_cost_nonnegative'),
		]


class TechnicianProfile(models.Model):
	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='technician_profile',
	)
	trade = models.CharField(max_length=30, blank=True)
	skills = models.JSONField(default=list, blank=True)
	rating_milli = models.PositiveIntegerField(default=4000)
	acceptance_milli = models.PositiveIntegerField(default=800)
	verified = models.BooleanField(default=True)
	available = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f'Technician {self.user_id}'


class MaintenanceComment(models.Model):
	request = models.ForeignKey(
		MaintenanceRequest,
		on_delete=models.CASCADE,
		related_name='comments',
	)
	author = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='maintenance_comments',
	)
	body = models.TextField()
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('created_at', 'pk')

	def __str__(self):
		return f'Comment {self.pk}'
