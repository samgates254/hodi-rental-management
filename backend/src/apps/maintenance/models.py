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
