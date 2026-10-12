from rest_framework import serializers

from apps.properties.models import Property, Unit

from .models import UtilityAccount, UtilityBill


class UtilityAccountSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    unit_name = serializers.CharField(source='unit.name', read_only=True, default='')

    class Meta:
        model = UtilityAccount
        fields = (
            'id', 'organization', 'property', 'property_name', 'unit', 'unit_name',
            'service_type', 'provider_name', 'service_reference', 'meter_reference',
            'responsible_party', 'is_active', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'property_name', 'unit_name', 'created_at', 'updated_at')

    def validate(self, attrs):
        organization = attrs.get('organization', getattr(self.instance, 'organization', None))
        property_record = attrs.get('property', getattr(self.instance, 'property', None))
        unit = attrs.get('unit', getattr(self.instance, 'unit', None))
        if property_record and organization and property_record.organization_id != organization.pk:
            raise serializers.ValidationError({'property': 'Property must belong to this organization.'})
        if unit and property_record and unit.building.property_id != property_record.pk:
            raise serializers.ValidationError({'unit': 'Unit must belong to the selected property.'})
        return attrs


class UtilityBillSerializer(serializers.ModelSerializer):
    account_name = serializers.SerializerMethodField()
    property_name = serializers.CharField(source='account.property.name', read_only=True)
    unit_name = serializers.CharField(source='account.unit.name', read_only=True, default='')
    service_type = serializers.CharField(source='account.service_type', read_only=True)
    responsible_party = serializers.CharField(source='account.responsible_party', read_only=True)

    class Meta:
        model = UtilityBill
        fields = (
            'id', 'account', 'account_name', 'property_name', 'unit_name', 'service_type',
            'responsible_party', 'period_start', 'period_end', 'due_date', 'amount_minor',
            'currency', 'reading_start', 'reading_end', 'reading_unit', 'document_reference',
            'notes', 'created_at',
        )
        read_only_fields = ('id', 'account_name', 'property_name', 'unit_name', 'service_type', 'responsible_party', 'created_at')

    def get_account_name(self, bill):
        return bill.account.provider_name

    def validate_account(self, account):
        if not account.is_active:
            raise serializers.ValidationError('Cannot record a bill against an inactive utility account.')
        request = self.context.get('request')
        if request and account.organization_id not in set(
            request.user.organization_memberships.filter(is_active=True).values_list('organization_id', flat=True)
        ):
            raise serializers.ValidationError('Utility account is not available to this user.')
        return account

    def validate(self, attrs):
        start = attrs.get('period_start', getattr(self.instance, 'period_start', None))
        end = attrs.get('period_end', getattr(self.instance, 'period_end', None))
        if start and end and end < start:
            raise serializers.ValidationError({'period_end': 'Period end must be on or after period start.'})
        reading_start = attrs.get('reading_start', getattr(self.instance, 'reading_start', None))
        reading_end = attrs.get('reading_end', getattr(self.instance, 'reading_end', None))
        if reading_start is not None and reading_end is not None and reading_end < reading_start:
            raise serializers.ValidationError({'reading_end': 'Reading cannot be lower than the starting reading.'})
        return attrs
