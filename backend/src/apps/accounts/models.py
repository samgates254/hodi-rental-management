from django.conf import settings
from django.db import models

from apps.organizations.models import Organization


class AccountProfile(models.Model):
	class AccountType(models.TextChoices):
		UNSPECIFIED = 'UNSPECIFIED', 'Unspecified'
		TENANT = 'TENANT', 'Tenant'
		OWNER = 'OWNER', 'Organization owner'
		SERVICE_PROFESSIONAL = 'SERVICE_PROFESSIONAL', 'Service professional'
		PROPERTY_AGENT = 'PROPERTY_AGENT', 'Property agent'

	class ProfessionalTrade(models.TextChoices):
		ELECTRICIAN = 'ELECTRICIAN', 'Electrician'
		CARPENTER = 'CARPENTER', 'Carpenter'
		PLUMBER = 'PLUMBER', 'Plumber'
		PAINTER = 'PAINTER', 'Painter'
		MASON = 'MASON', 'Mason'
		OTHER = 'OTHER', 'Other repair professional'

	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name='account_profile',
	)
	account_type = models.CharField(
		max_length=30,
		choices=AccountType.choices,
		default=AccountType.UNSPECIFIED,
	)
	organization = models.ForeignKey(
		Organization,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='account_profiles',
	)
	organization_name = models.CharField(max_length=200, blank=True)
	professional_trade = models.CharField(
		max_length=30,
		choices=ProfessionalTrade.choices,
		blank=True,
	)
	phone_number = models.CharField(max_length=30, blank=True)
	email_verified_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('user__username',)

	def __str__(self):
		return f'Account profile for {self.user}'
