from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.properties.models import Unit
from apps.tenants.models import Tenant


class Lease(models.Model):
	class Status(models.TextChoices):
		DRAFT = 'DRAFT', 'Draft'
		ACTIVE = 'ACTIVE', 'Active'
		TERMINATED = 'TERMINATED', 'Terminated'
		EXPIRED = 'EXPIRED', 'Expired'

	tenant = models.ForeignKey(
		Tenant,
		on_delete=models.PROTECT,
		related_name='leases',
	)
	unit = models.ForeignKey(
		Unit,
		on_delete=models.PROTECT,
		related_name='leases',
	)
	reference = models.CharField(max_length=100)
	start_date = models.DateField()
	end_date = models.DateField(null=True, blank=True)
	monthly_rent_minor = models.PositiveBigIntegerField()
	security_deposit_minor = models.PositiveBigIntegerField(default=0)
	status = models.CharField(
		max_length=20,
		choices=Status.choices,
		default=Status.DRAFT,
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=('tenant', 'reference'),
				name='unique_lease_reference_per_tenant',
			),
			models.CheckConstraint(
				check=models.Q(end_date__isnull=True)
				| models.Q(end_date__gt=models.F('start_date')),
				name='lease_end_after_start',
			),
		]
		ordering = ('-start_date',)

	@property
	def organization_id(self):
		return self.tenant.organization_id

	def clean(self):
		super().clean()

		if self.tenant_id and self.unit_id:
			if self.tenant.organization_id != self.unit.organization_id:
				raise ValidationError(
					'Tenant and unit must belong to the same organization.',
				)

		if not self.unit_id or not self.start_date:
			return

		# Lease dates are inclusive civil dates. If one lease ends on a given
		# day, another lease for the unit may begin only on the following day.
		overlapping = Lease.objects.filter(
			unit_id=self.unit_id,
			start_date__lte=self.end_date or date.max,
		).filter(
			models.Q(end_date__isnull=True)
			| models.Q(end_date__gte=self.start_date),
		)
		if self.pk:
			overlapping = overlapping.exclude(pk=self.pk)
		if overlapping.exists():
			raise ValidationError('This unit already has an overlapping lease.')

	def __str__(self):
		return self.reference


class RentSchedule(models.Model):
	class Frequency(models.TextChoices):
		MONTHLY = 'MONTHLY', 'Monthly'
		WEEKLY = 'WEEKLY', 'Weekly'
		QUARTERLY = 'QUARTERLY', 'Quarterly'

	lease = models.ForeignKey(
		Lease,
		on_delete=models.PROTECT,
		related_name='rent_schedules',
	)
	effective_from = models.DateField()
	effective_to = models.DateField(null=True, blank=True)
	amount_minor = models.PositiveBigIntegerField()
	frequency = models.CharField(
		max_length=20,
		choices=Frequency.choices,
		default=Frequency.MONTHLY,
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.CheckConstraint(
				check=models.Q(effective_to__isnull=True)
				| models.Q(effective_to__gt=models.F('effective_from')),
				name='rent_schedule_end_after_start',
			),
		]
		ordering = ('effective_from',)

	def clean(self):
		super().clean()
		if not self.lease_id or not self.effective_from:
			return

		overlapping = RentSchedule.objects.filter(
			lease_id=self.lease_id,
			effective_from__lt=self.effective_to or date.max,
		).filter(
			models.Q(effective_to__isnull=True)
			| models.Q(effective_to__gt=self.effective_from),
		)
		if self.pk:
			overlapping = overlapping.exclude(pk=self.pk)
		if overlapping.exists():
			raise ValidationError('This lease already has an overlapping rent schedule.')

	def __str__(self):
		return f'{self.lease.reference} - {self.effective_from}'


class LeaseAmendment(models.Model):
	class AmendmentType(models.TextChoices):
		RENT_CHANGE = 'RENT_CHANGE', 'Rent change'
		DATE_CHANGE = 'DATE_CHANGE', 'Date change'
		DEPOSIT_CHANGE = 'DEPOSIT_CHANGE', 'Deposit change'
		TERMINATION = 'TERMINATION', 'Termination'
		OTHER = 'OTHER', 'Other'

	lease = models.ForeignKey(
		Lease,
		on_delete=models.PROTECT,
		related_name='amendments',
	)
	amendment_type = models.CharField(max_length=30, choices=AmendmentType.choices)
	effective_date = models.DateField()
	reason = models.TextField(blank=True)
	before_state = models.JSONField(default=dict)
	after_state = models.JSONField(default=dict)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='lease_amendments',
	)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('-effective_date', '-created_at')

	def __str__(self):
		return f'{self.lease.reference} - {self.amendment_type}'
