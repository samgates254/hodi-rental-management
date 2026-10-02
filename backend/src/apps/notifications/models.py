from django.conf import settings
from django.db import models


class Notification(models.Model):
	class Type(models.TextChoices):
		PAYMENT_RECEIVED = 'PAYMENT_RECEIVED', 'Payment received'
		MAINTENANCE_ASSIGNED = 'MAINTENANCE_ASSIGNED', 'Maintenance assigned'
		MAINTENANCE_UPDATED = 'MAINTENANCE_UPDATED', 'Maintenance updated'
		LEASE_ACTIVATED = 'LEASE_ACTIVATED', 'Lease activated'
		LEASE_TERMINATED = 'LEASE_TERMINATED', 'Lease terminated'
		INVOICE_POSTED = 'INVOICE_POSTED', 'Invoice posted'
		MEMBERSHIP_CHANGED = 'MEMBERSHIP_CHANGED', 'Membership changed'

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='notifications',
	)
	organization = models.ForeignKey(
		'organizations.Organization',
		on_delete=models.CASCADE,
		null=True,
		blank=True,
		related_name='notifications',
	)
	type = models.CharField(max_length=40)
	title = models.CharField(max_length=200)
	body = models.TextField(blank=True)
	payload = models.JSONField(default=dict, blank=True)
	read_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('-created_at', 'pk')
		indexes = [
			models.Index(
				fields=('user', 'read_at', '-created_at'),
				name='notif_user_read_created_idx',
			),
		]

	def __str__(self):
		return self.title
