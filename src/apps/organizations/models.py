from django.conf import settings
from django.db import models


class Organization(models.Model):
	name = models.CharField(max_length=200)
	slug = models.SlugField(max_length=80, unique=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('name',)

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
