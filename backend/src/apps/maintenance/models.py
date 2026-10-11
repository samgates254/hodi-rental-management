from django.db import models
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
