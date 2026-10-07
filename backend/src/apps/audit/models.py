from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AuditLog(models.Model):
	actor = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='audit_logs',
	)
	organization = models.ForeignKey(
		'organizations.Organization',
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='audit_logs',
	)
	action = models.CharField(max_length=80)
	object_type = models.CharField(max_length=80)
	object_id = models.CharField(max_length=64)
	metadata = models.JSONField(default=dict, blank=True)
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('-created_at', 'pk')
		indexes = [
			models.Index(fields=('organization', 'object_type', 'object_id'), name='audit_org_object_idx'),
		]

	def save(self, *args, **kwargs):
		if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
			raise ValidationError('Audit logs are append-only.')
		super().save(*args, **kwargs)

	def delete(self, *args, **kwargs):
		raise ValidationError('Audit logs are append-only.')

	def __str__(self):
		return f'{self.action} {self.object_type}:{self.object_id}'
