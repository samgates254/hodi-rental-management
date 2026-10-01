from django.conf import settings
from django.db import models

from apps.organizations.models import Organization


class Tenant(models.Model):
	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='tenant_record',
	)
	organization = models.ForeignKey(
		Organization,
		on_delete=models.CASCADE,
		related_name='tenants',
	)
	first_name = models.CharField(max_length=100)
	last_name = models.CharField(max_length=100)
	phone_number = models.CharField(max_length=30)
	email = models.EmailField(blank=True)
	national_id = models.CharField(max_length=50, blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('last_name', 'first_name')
		indexes = [
			models.Index(fields=('organization', 'phone_number')),
		]

	@property
	def full_name(self):
		return f'{self.first_name} {self.last_name}'.strip()

	def __str__(self):
		return self.full_name
