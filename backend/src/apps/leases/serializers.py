from rest_framework import serializers

from .models import Lease, LeaseAmendment, RentSchedule


class LeaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lease
        fields = ('id', 'tenant', 'unit', 'reference', 'start_date', 'end_date', 'monthly_rent_minor', 'security_deposit_minor', 'status', 'created_at', 'updated_at')
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


class LeaseAmendmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaseAmendment
        fields = ('id', 'lease', 'amendment_type', 'effective_date', 'reason', 'before_state', 'after_state', 'created_by', 'created_at')
        read_only_fields = ('id', 'created_at', 'created_by')
