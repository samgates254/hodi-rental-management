import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

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


CHARGE_TYPES = (
	'WATER',
	'ELECTRICITY',
	'SEWER',
	'GAS',
	'UTILITY',
	'SERVICE_CHARGE',
	'GARBAGE',
	'SECURITY',
	'MANDATORY_SERVICE',
	'PENALTY',
	'LATE_FEE',
	'FINE',
	'RENT',
	'BASE_RENT',
	'DEPOSIT',
	'SECURITY_DEPOSIT',
	'MISC',
	'OTHER',
)


class DocumentStatus(models.TextChoices):
	DRAFT = 'DRAFT', 'Draft'
	POSTED = 'POSTED', 'Posted'
	VOIDED = 'VOIDED', 'Voided'
	WRITTEN_OFF = 'WRITTEN_OFF', 'Written off'


class Invoice(models.Model):
	organization = models.ForeignKey(
		'organizations.Organization',
		on_delete=models.PROTECT,
		related_name='invoices',
	)
	tenant = models.ForeignKey(
		'tenants.Tenant',
		on_delete=models.PROTECT,
		related_name='invoices',
	)
	lease = models.ForeignKey(
		Lease,
		on_delete=models.PROTECT,
		null=True,
		blank=True,
		related_name='invoices',
	)
	period_start = models.DateField()
	period_end = models.DateField()
	due_date = models.DateField()
	status = models.CharField(
		max_length=20,
		choices=DocumentStatus.choices,
		default=DocumentStatus.DRAFT,
	)
	currency = models.CharField(max_length=3, default='KES')
	total_cents = models.PositiveBigIntegerField(default=0)
	balance_cents = models.PositiveBigIntegerField(default=0)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('-period_start', '-id')
		constraints = [
			models.CheckConstraint(
				check=Q(period_end__gte=models.F('period_start')),
				name='invoice_period_end_on_or_after_start',
			),
		]

	def __str__(self):
		return f'Invoice {self.pk} ({self.status})'


class Charge(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	invoice = models.ForeignKey(
		Invoice,
		on_delete=models.PROTECT,
		related_name='charges',
	)
	organization = models.ForeignKey(
		'organizations.Organization',
		on_delete=models.PROTECT,
		related_name='charges',
	)
	tenant = models.ForeignKey(
		'tenants.Tenant',
		on_delete=models.PROTECT,
		related_name='charges',
	)
	charge_type = models.CharField(max_length=32)
	description = models.TextField(blank=True)
	amount_cents = models.PositiveBigIntegerField()
	balance_cents = models.PositiveBigIntegerField()
	due_date = models.DateField()
	period_start = models.DateField(null=True, blank=True)
	lifecycle = models.CharField(
		max_length=20,
		choices=DocumentStatus.choices,
		default=DocumentStatus.DRAFT,
	)
	currency = models.CharField(max_length=3, default='KES')
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('due_date', 'created_at')
		constraints = [
			models.CheckConstraint(
				check=Q(balance_cents__lte=models.F('amount_cents')),
				name='charge_balance_lte_amount',
			),
		]

	def __str__(self):
		return f'{self.charge_type} {self.amount_cents}'


class Payment(models.Model):
	class Method(models.TextChoices):
		CASH = 'CASH', 'Cash'
		BANK_TRANSFER = 'BANK_TRANSFER', 'Bank transfer'
		MPESA = 'MPESA', 'M-Pesa'
		OTHER = 'OTHER', 'Other'

	class Status(models.TextChoices):
		PENDING = 'PENDING', 'Pending'
		ALLOCATED = 'ALLOCATED', 'Allocated'
		FAILED = 'FAILED', 'Failed'
		VOIDED = 'VOIDED', 'Voided'

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	organization = models.ForeignKey(
		'organizations.Organization',
		on_delete=models.PROTECT,
		related_name='ledger_payments',
	)
	tenant = models.ForeignKey(
		'tenants.Tenant',
		on_delete=models.PROTECT,
		related_name='ledger_payments',
	)
	amount_cents = models.PositiveBigIntegerField()
	allocated_cents = models.PositiveBigIntegerField(default=0)
	overpayment_cents = models.PositiveBigIntegerField(default=0)
	received_date = models.DateField()
	execution_timestamp = models.DateTimeField()
	method = models.CharField(max_length=20, choices=Method.choices)
	status = models.CharField(
		max_length=20,
		choices=Status.choices,
		default=Status.PENDING,
	)
	currency = models.CharField(max_length=3, default='KES')
	reference = models.CharField(max_length=100, blank=True)
	external_id = models.CharField(max_length=100, blank=True)
	recorded_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='recorded_ledger_payments',
	)
	policy_id = models.CharField(max_length=40, blank=True)
	policy_version = models.PositiveIntegerField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('-received_date', '-created_at')
		constraints = [
			models.UniqueConstraint(
				fields=('organization', 'external_id'),
				condition=~Q(external_id=''),
				name='unique_ledger_payment_external_id_per_org',
			),
			models.UniqueConstraint(
				fields=('organization', 'reference'),
				condition=~Q(reference=''),
				name='unique_ledger_payment_reference_per_org',
			),
			models.CheckConstraint(
				check=Q(amount_cents__gt=0),
				name='ledger_payment_amount_positive',
			),
		]

	def __str__(self):
		return f'Payment {self.pk}'


class PaymentAllocation(models.Model):
	payment = models.ForeignKey(
		Payment,
		on_delete=models.PROTECT,
		related_name='allocations',
	)
	charge = models.ForeignKey(
		Charge,
		on_delete=models.PROTECT,
		related_name='allocations',
	)
	amount_cents = models.PositiveBigIntegerField()
	policy_id = models.CharField(max_length=40)
	policy_version = models.PositiveIntegerField()
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=('payment', 'charge'),
				name='unique_allocation_per_payment_charge',
			),
		]
		ordering = ('created_at', 'pk')

	def __str__(self):
		return f'{self.payment_id} -> {self.charge_id}'


class LedgerPosting(models.Model):
	payment = models.ForeignKey(
		Payment,
		on_delete=models.PROTECT,
		related_name='postings',
	)
	account = models.CharField(max_length=8)
	direction = models.CharField(max_length=8)
	amount_cents = models.PositiveBigIntegerField()
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('pk',)

	def __str__(self):
		return f'{self.direction} {self.account} {self.amount_cents}'
