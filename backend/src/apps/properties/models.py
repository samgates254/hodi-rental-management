from django.db import models

from apps.organizations.models import Organization


class Property(models.Model):
	organization = models.ForeignKey(
		Organization,
		on_delete=models.CASCADE,
		related_name='properties',
	)
	name = models.CharField(max_length=200)
	address = models.TextField(blank=True)
	city = models.CharField(max_length=100, default='Ongata Rongai')
	country = models.CharField(max_length=100, default='Kenya')
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=('organization', 'name'),
				name='unique_property_name_per_organization',
			),
		]
		ordering = ('name',)

	def __str__(self):
		return self.name


class Building(models.Model):
	property = models.ForeignKey(
		Property,
		on_delete=models.CASCADE,
		related_name='buildings',
	)
	name = models.CharField(max_length=200)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=('property', 'name'),
				name='unique_building_name_per_property',
			),
		]
		ordering = ('name',)

	def __str__(self):
		return f'{self.property} - {self.name}'


class Unit(models.Model):
	class Status(models.TextChoices):
		AVAILABLE = 'AVAILABLE', 'Available'
		OCCUPIED = 'OCCUPIED', 'Occupied'
		MAINTENANCE = 'MAINTENANCE', 'Maintenance'
		INACTIVE = 'INACTIVE', 'Inactive'

	building = models.ForeignKey(
		Building,
		on_delete=models.CASCADE,
		related_name='units',
	)
	name = models.CharField(max_length=100)
	status = models.CharField(
		max_length=20,
		choices=Status.choices,
		default=Status.AVAILABLE,
	)
	bedrooms = models.PositiveSmallIntegerField(default=0)
	metadata = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=('building', 'name'),
				name='unique_unit_name_per_building',
			),
		]
		ordering = ('building', 'name')

	@property
	def organization_id(self):
		return self.building.property.organization_id

	def __str__(self):
		return f'{self.building} - {self.name}'
