from django.conf import settings
from django.db import models

from apps.leases.models import Lease


class RentPayment(models.Model):
	class Status(models.TextChoices):
		PENDING = 'PENDING', 'Pending'
		PAID = 'PAID', 'Paid'
		OVERDUE = 'OVERDUE', 'Overdue'

	lease = models.ForeignKey(
		Lease,
		on_delete=models.PROTECT,
		related_name='payments',
	)
	recorded_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='recorded_rent_payments',
	)
	due_date = models.DateField()
	amount_minor = models.PositiveBigIntegerField()
	status = models.CharField(
		max_length=20,
		choices=Status.choices,
		default=Status.PENDING,
	)
	paid_at = models.DateTimeField(null=True, blank=True)
	method = models.CharField(max_length=40, blank=True)
	reference = models.CharField(max_length=100, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('due_date', '-created_at')

	@property
	def organization_id(self):
		return self.lease.organization_id

	def __str__(self):
		return f'{self.lease.reference} - {self.due_date}'
