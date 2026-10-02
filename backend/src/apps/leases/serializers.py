from rest_framework import serializers

from .models import Lease, LeaseAmendment, RentSchedule


class LeaseSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    property_name = serializers.CharField(source='unit.building.property.name', read_only=True)
    property_city = serializers.CharField(source='unit.building.property.city', read_only=True)
    organization_name = serializers.CharField(source='tenant.organization.name', read_only=True)
    tenant_name = serializers.CharField(source='tenant.full_name', read_only=True)

    class Meta:
        model = Lease
        fields = (
            'id', 'tenant', 'tenant_name', 'unit', 'unit_name', 'property_name',
            'property_city', 'organization_name', 'reference', 'start_date', 'end_date',
            'monthly_rent_minor', 'security_deposit_minor', 'status', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate(self, attrs):
        tenant = attrs.get('tenant', getattr(self.instance, 'tenant', None))
        unit = attrs.get('unit', getattr(self.instance, 'unit', None))
        if tenant and unit and tenant.organization_id != unit.organization_id:
            raise serializers.ValidationError('Tenant and unit must belong to the same organization.')
        return attrs


class RentScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RentSchedule
        fields = ('id', 'lease', 'effective_from', 'effective_to', 'amount_minor', 'frequency', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class LeaseTerminateSerializer(serializers.Serializer):
    end_date = serializers.DateField()
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class LeaseAmendmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaseAmendment
        fields = ('id', 'lease', 'amendment_type', 'effective_date', 'reason', 'before_state', 'after_state', 'created_by', 'created_at')
        read_only_fields = ('id', 'created_at', 'created_by')
