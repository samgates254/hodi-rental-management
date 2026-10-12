from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.organizations.models import Organization
from apps.properties.models import Property, Unit


class UtilityAccount(models.Model):
    class ServiceType(models.TextChoices):
        ELECTRICITY = 'ELECTRICITY', 'Electricity'
        WATER = 'WATER', 'Water'
        GAS = 'GAS', 'Gas'
        INTERNET = 'INTERNET', 'Internet'
        OTHER = 'OTHER', 'Other'

    class ResponsibleParty(models.TextChoices):
        LANDLORD = 'LANDLORD', 'Landlord'
        TENANT = 'TENANT', 'Tenant'

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='utility_accounts',
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.PROTECT,
        related_name='utility_accounts',
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='utility_accounts',
    )
    service_type = models.CharField(max_length=16, choices=ServiceType.choices)
    provider_name = models.CharField(max_length=160)
    service_reference = models.CharField(max_length=120, blank=True)
    meter_reference = models.CharField(max_length=120, blank=True)
    responsible_party = models.CharField(
        max_length=12,
        choices=ResponsibleParty.choices,
        default=ResponsibleParty.LANDLORD,
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_utility_accounts',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('property__name', 'unit__name', 'service_type', 'pk')
        indexes = [models.Index(fields=('organization', 'is_active'), name='utility_org_active_idx')]

    def clean(self):
        if self.property_id and self.organization_id != self.property.organization_id:
            raise ValidationError({'property': 'Property must belong to this organization.'})
        if self.unit_id and self.unit.building.property_id != self.property_id:
            raise ValidationError({'unit': 'Unit must belong to the selected property.'})

    def __str__(self):
        return f'{self.get_service_type_display()} · {self.property}'


class UtilityBill(models.Model):
    account = models.ForeignKey(
        UtilityAccount,
        on_delete=models.PROTECT,
        related_name='bills',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default='KES')
    reading_start = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    reading_end = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    reading_unit = models.CharField(max_length=24, blank=True)
    document_reference = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='recorded_utility_bills',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-period_end', '-pk')
        constraints = [
            models.CheckConstraint(
                condition=Q(period_end__gte=models.F('period_start')),
                name='utility_bill_period_valid',
            ),
            models.UniqueConstraint(
                fields=('account', 'period_start', 'period_end'),
                name='unique_utility_bill_period',
            ),
        ]
        indexes = [models.Index(fields=('account', '-period_end'), name='util_bill_account_period_idx')]

    @property
    def organization_id(self):
        return self.account.organization_id

    def clean(self):
        if self.reading_start is not None and self.reading_end is not None:
            if self.reading_end < self.reading_start:
                raise ValidationError({'reading_end': 'Reading cannot be lower than the starting reading.'})

    def __str__(self):
        return f'{self.account} · {self.period_start}–{self.period_end}'
