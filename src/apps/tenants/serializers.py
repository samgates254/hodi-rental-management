from rest_framework import serializers

from .models import Tenant


class TenantSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = Tenant
        fields = ('id', 'organization', 'first_name', 'last_name', 'full_name', 'phone_number', 'email', 'national_id', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('id', 'full_name', 'created_at', 'updated_at')
