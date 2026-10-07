from rest_framework import serializers

from common.permissions import user_can_access_organization_resource

from .models import Tenant


class TenantSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Tenant
        fields = (
            'id', 'organization', 'user', 'first_name', 'last_name', 'full_name',
            'phone_number', 'email', 'national_id', 'is_active', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'user', 'full_name', 'created_at', 'updated_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if getattr(self, 'instance', None) is not None and not isinstance(self.instance, list):
            self.fields['organization'].read_only = True

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user is None or not getattr(user, 'is_authenticated', False):
            return data
        if instance.user_id == user.id:
            return data
        # Operational roles (caretaker) may see contact details, not government ID.
        # Owners, managers, and billing readers keep the identifier.
        privileged = user_can_access_organization_resource(
            user,
            instance.organization_id,
            'tenants',
            'write',
        ) or user_can_access_organization_resource(
            user,
            instance.organization_id,
            'billing',
            'read',
        )
        if not privileged:
            data['national_id'] = ''
        return data