from rest_framework import serializers

from apps.properties.models import Unit
from apps.tenants.models import Tenant

from .models import MaintenanceComment, MaintenanceRequest, WorkOrder


class MaintenanceCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceComment
        fields = ('id', 'author', 'author_name', 'body', 'created_at')
        read_only_fields = ('id', 'author', 'author_name', 'created_at')

    def get_author_name(self, comment):
        return comment.author.get_full_name() or comment.author.get_username()


class WorkOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkOrder
        fields = (
            'id', 'request', 'assignee', 'status', 'assigned_at', 'completed_at',
            'notes', 'created_at', 'updated_at',
        )
        read_only_fields = fields


class MaintenanceRequestSerializer(serializers.ModelSerializer):
    organization = serializers.IntegerField(source='organization_id', read_only=True)
    comments = MaintenanceCommentSerializer(many=True, read_only=True)
    work_order = WorkOrderSerializer(read_only=True)

    class Meta:
        model = MaintenanceRequest
        fields = (
            'id', 'organization', 'unit', 'tenant', 'created_by', 'title', 'description',
            'hazard', 'vulnerability', 'status', 'priority_class', 'score_millis',
            'emergency_override', 'completed_at', 'closed_at', 'work_order', 'comments',
            'created_at', 'updated_at',
        )
        read_only_fields = fields


class MaintenanceRequestWriteSerializer(serializers.Serializer):
    unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all(), required=False)
    tenant = serializers.PrimaryKeyRelatedField(
        queryset=Tenant.objects.all(),
        required=False,
        allow_null=True,
    )
    title = serializers.CharField(max_length=200)
    description = serializers.CharField()
    hazard = serializers.IntegerField(min_value=1, max_value=5)
    vulnerability = serializers.IntegerField(min_value=1, max_value=5, required=False, default=1)
    building_age_years = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    age_band_value = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=5)


class MaintenanceRequestUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False)
    hazard = serializers.IntegerField(min_value=1, max_value=5, required=False)
    vulnerability = serializers.IntegerField(min_value=1, max_value=5, required=False)
    building_age_years = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    age_band_value = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=5)


class AssignSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False)
    technician_id = serializers.IntegerField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs.get('user_id') is None and attrs.get('technician_id') is None:
            raise serializers.ValidationError('user_id or technician_id is required.')
        return attrs


class CommentWriteSerializer(serializers.Serializer):
    body = serializers.CharField()
