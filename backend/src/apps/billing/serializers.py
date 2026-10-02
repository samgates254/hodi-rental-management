from rest_framework import serializers

from .models import RentPayment


class RentPaymentSerializer(serializers.ModelSerializer):
	organization = serializers.IntegerField(source='lease.tenant.organization_id', read_only=True)
	tenant_name = serializers.CharField(source='lease.tenant.full_name', read_only=True)
	unit_name = serializers.CharField(source='lease.unit.name', read_only=True)
	lease_reference = serializers.CharField(source='lease.reference', read_only=True)

	class Meta:
		model = RentPayment
		fields = (
			'id', 'organization', 'lease', 'lease_reference', 'tenant_name',
			'unit_name', 'recorded_by', 'due_date', 'amount_minor', 'status',
			'paid_at', 'method', 'reference', 'created_at', 'updated_at',
		)
		read_only_fields = ('id', 'recorded_by', 'created_at', 'updated_at')

	def validate_amount_minor(self, amount):
		if amount <= 0:
			raise serializers.ValidationError('Amount must be greater than zero.')
		return amount
