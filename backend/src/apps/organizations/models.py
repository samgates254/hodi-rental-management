from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils.text import slugify


class Organization(models.Model):
	name = models.CharField(max_length=200)
	slug = models.SlugField(max_length=80, unique=True, blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('name',)

	def _build_unique_slug(self):
		"""Derive a non-empty unique slug from name (never leave blank)."""
		base_slug = slugify(self.name or '')[:80] or 'organization'
		candidate = base_slug
		counter = 2
		while Organization.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
			suffix = f'-{counter}'
			candidate = f'{base_slug[: max(1, 80 - len(suffix))]}{suffix}'
			counter += 1
			if counter > 10_000:
				# Extremely unlikely; fall back to pk-ish uniqueness via timestamp-free loop break
				import uuid
				candidate = f'{base_slug[:70]}-{uuid.uuid4().hex[:8]}'
				break
		return candidate

	def save(self, *args, **kwargs):
		# Always ensure slug is non-empty before INSERT/UPDATE (unique + blank would still
		# allow multiple empty strings on some backends / fail UNIQUE on SQLite).
		if not (self.slug or '').strip():
			self.slug = self._build_unique_slug()

		max_attempts = 5
		for attempt in range(max_attempts):
			try:
				with transaction.atomic():
					super().save(*args, **kwargs)
				return
			except IntegrityError:
				# Race on unique slug — regenerate and retry.
				if attempt >= max_attempts - 1:
					raise
				self.slug = self._build_unique_slug()

	def __str__(self):
		return self.name


class OrganizationMembership(models.Model):
	class Role(models.TextChoices):
		OWNER = 'OWNER', 'Organization owner'
		PROPERTY_MANAGER = 'PROPERTY_MANAGER', 'Property manager'
		ACCOUNTANT = 'ACCOUNTANT', 'Accountant'
		CARETAKER = 'CARETAKER', 'Caretaker'
		TECHNICIAN = 'TECHNICIAN', 'Technician'
		SUPPORT = 'SUPPORT', 'Support'

	organization = models.ForeignKey(
		Organization,
		on_delete=models.CASCADE,
		related_name='memberships',
	)
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='organization_memberships',
	)
	role = models.CharField(max_length=30, choices=Role.choices)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=('organization', 'user'),
				name='unique_organization_membership',
			),
		]

	def __str__(self):
		return f'{self.user} - {self.organization} ({self.role})'
