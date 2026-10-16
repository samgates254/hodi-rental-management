import uuid

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
		DRAFT = 'DRAFT', 'Draft'
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


class RepairQuotationLine(models.Model):
	class Category(models.TextChoices):
		MATERIAL = 'MATERIAL', 'Material'
		LABOUR = 'LABOUR', 'Labour'
		TRANSPORT = 'TRANSPORT', 'Transport'
		OTHER = 'OTHER', 'Other'

	quotation = models.ForeignKey(RepairQuotation, on_delete=models.PROTECT, related_name='lines')
	category = models.CharField(max_length=12, choices=Category.choices)
	description = models.CharField(max_length=240)
	quantity = models.DecimalField(max_digits=12, decimal_places=3)
	unit = models.CharField(max_length=30)
	unit_price_cents = models.PositiveBigIntegerField()
	line_total_cents = models.PositiveBigIntegerField()
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('pk',)
		constraints = [
			models.CheckConstraint(condition=models.Q(quantity__gt=0), name='repair_quote_line_qty_positive'),
			models.CheckConstraint(condition=models.Q(unit_price_cents__gte=0), name='repair_quote_line_price_nonnegative'),
			models.CheckConstraint(condition=models.Q(line_total_cents__gte=0), name='repair_quote_line_total_nonnegative'),
		]


class JobMaterialPurchase(models.Model):
	class Status(models.TextChoices):
		RECORDED = 'RECORDED', 'Purchase recorded'
		PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Partially received'
		RECEIVED = 'RECEIVED', 'Received'

	organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT, related_name='job_material_purchases')
	maintenance_request = models.ForeignKey(MaintenanceRequest, on_delete=models.PROTECT, related_name='material_purchases')
	quotation = models.ForeignKey(RepairQuotation, on_delete=models.PROTECT, related_name='material_purchases')
	quotation_line = models.ForeignKey(RepairQuotationLine, on_delete=models.PROTECT, related_name='purchases')
	supplier_name = models.CharField(max_length=200)
	supplier_profile = models.ForeignKey('marketplace.SupplierProfile', on_delete=models.PROTECT, null=True, blank=True, related_name='material_purchases')
	supplier_reference = models.CharField(max_length=200, blank=True)
	description = models.CharField(max_length=240)
	quantity = models.DecimalField(max_digits=12, decimal_places=3)
	unit = models.CharField(max_length=30)
	unit_price_cents = models.PositiveBigIntegerField()
	purchase_total_cents = models.PositiveBigIntegerField()
	purchase_date = models.DateField()
	status = models.CharField(max_length=24, choices=Status.choices, default=Status.RECORDED)
	idempotency_key = models.UUIDField(default=uuid.uuid4)
	overrun_reason = models.TextField(blank=True)
	overrun_authorized_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
		related_name='authorized_material_purchase_overruns',
	)
	overrun_authorized_at = models.DateTimeField(null=True, blank=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='job_material_purchases_created')
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('created_at', 'pk')
		constraints = [
			models.UniqueConstraint(fields=('organization', 'idempotency_key'), name='job_material_purchase_idempotency_uniq'),
			models.CheckConstraint(condition=models.Q(quantity__gt=0), name='job_material_purchase_qty_positive'),
			models.CheckConstraint(condition=models.Q(unit_price_cents__gte=0), name='job_material_purchase_price_nonnegative'),
			models.CheckConstraint(condition=models.Q(purchase_total_cents__gte=0), name='job_material_purchase_total_nonnegative'),
		]


class JobMaterialReceipt(models.Model):
	purchase = models.ForeignKey(JobMaterialPurchase, on_delete=models.PROTECT, related_name='receipts')
	quantity = models.DecimalField(max_digits=12, decimal_places=3)
	evidence_reference = models.CharField(max_length=500)
	notes = models.CharField(max_length=500, blank=True)
	idempotency_key = models.UUIDField(default=uuid.uuid4)
	acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='job_material_receipts_acknowledged')
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('created_at', 'pk')
		constraints = [
			models.UniqueConstraint(fields=('purchase', 'idempotency_key'), name='job_material_receipt_idempotency_uniq'),
			models.CheckConstraint(condition=models.Q(quantity__gt=0), name='job_material_receipt_qty_positive'),
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
	cost_overrun_reason = models.TextField(blank=True)
	cost_overrun_authorized_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
		related_name='authorized_repair_cost_overruns',
	)
	cost_overrun_authorized_at = models.DateTimeField(null=True, blank=True)
	follow_up_required = models.BooleanField(default=False)
	follow_up_reason = models.CharField(max_length=500, blank=True)

	class Meta:
		ordering = ('-submitted_at', '-pk')
		constraints = [
			models.CheckConstraint(condition=models.Q(labour_cost_cents__gte=0), name='repair_completion_labour_nonnegative'),
			models.CheckConstraint(condition=models.Q(materials_cost_cents__gte=0), name='repair_completion_materials_nonnegative'),
			models.CheckConstraint(condition=models.Q(other_cost_cents__gte=0), name='repair_completion_other_nonnegative'),
		]


class RepairCompletionEvidence(models.Model):
	class Category(models.TextChoices):
		BEFORE_PHOTO = 'BEFORE_PHOTO', 'Before-work evidence'
		AFTER_PHOTO = 'AFTER_PHOTO', 'After-work photograph'
		WORK_DOCUMENT = 'WORK_DOCUMENT', 'Work document'
		MATERIAL_RECEIPT = 'MATERIAL_RECEIPT', 'Material receipt evidence'
		OTHER = 'OTHER', 'Other completion evidence'

	completion = models.ForeignKey(RepairCompletion, on_delete=models.PROTECT, related_name='evidence')
	maintenance_request = models.ForeignKey(MaintenanceRequest, on_delete=models.PROTECT, related_name='completion_evidence')
	organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT, related_name='repair_completion_evidence')
	category = models.CharField(max_length=24, choices=Category.choices)
	caption = models.CharField(max_length=240, blank=True)
	evidence_reference = models.CharField(max_length=500)
	recorded_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='repair_completion_evidence_recorded',
	)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('created_at', 'pk')
		constraints = [
			models.UniqueConstraint(fields=('completion', 'evidence_reference'), name='repair_completion_evidence_ref_uniq'),
		]


class TurnoverAssessment(models.Model):
	class Status(models.TextChoices):
		REQUESTED = 'REQUESTED', 'Inspection requested'
		FAILED = 'FAILED', 'Not ready'
		READY = 'READY', 'Ready for next tenancy'

	organization = models.ForeignKey('organizations.Organization', on_delete=models.PROTECT, related_name='turnover_assessments')
	property = models.ForeignKey('properties.Property', on_delete=models.PROTECT, related_name='turnover_assessments')
	building = models.ForeignKey('properties.Building', on_delete=models.PROTECT, related_name='turnover_assessments')
	unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name='turnover_assessments')
	maintenance_request = models.ForeignKey(MaintenanceRequest, on_delete=models.PROTECT, related_name='turnover_assessments')
	revision_of = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='reassessments')
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)
	outstanding_issues = models.TextField(blank=True)
	requested_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='turnover_assessments_requested',
	)
	requested_at = models.DateTimeField(auto_now_add=True)
	assessed_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
		related_name='turnover_assessments_performed',
	)
	assessed_at = models.DateTimeField(null=True, blank=True)
	idempotency_key = models.UUIDField(default=uuid.uuid4)

	class Meta:
		ordering = ('-requested_at', '-pk')
		constraints = [
			models.UniqueConstraint(fields=('organization', 'idempotency_key'), name='turnover_assessment_idempotency_uniq'),
		]


class TurnoverChecklistItem(models.Model):
	assessment = models.ForeignKey(TurnoverAssessment, on_delete=models.PROTECT, related_name='checklist_items')
	item_key = models.SlugField(max_length=50)
	label = models.CharField(max_length=160)
	passed = models.BooleanField()
	notes = models.CharField(max_length=500, blank=True)

	class Meta:
		ordering = ('pk',)
		constraints = [
			models.UniqueConstraint(fields=('assessment', 'item_key'), name='turnover_checklist_item_key_uniq'),
		]


class RepairMaterialUsed(models.Model):
	completion = models.ForeignKey(RepairCompletion, on_delete=models.PROTECT, related_name='materials')
	description = models.CharField(max_length=200)
	quantity = models.DecimalField(max_digits=12, decimal_places=3)
	unit = models.CharField(max_length=30)
	unit_cost_cents = models.PositiveBigIntegerField(default=0)
	purchase = models.ForeignKey(
		JobMaterialPurchase, on_delete=models.PROTECT, null=True, blank=True,
		related_name='material_uses',
	)

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
	verified = models.BooleanField(default=False)
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
