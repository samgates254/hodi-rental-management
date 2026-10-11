from rest_framework import serializers
from decimal import Decimal

from apps.properties.models import Unit
from apps.tenants.models import Tenant

from .models import (
    MaintenanceComment, MaintenanceRequest, RepairCompletion, RepairMaterialUsed,
    RepairQuotation, WorkOrder,
)


class MaintenanceCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceComment
        fields = ('id', 'author', 'author_name', 'body', 'created_at')
        read_only_fields = ('id', 'author', 'author_name', 'created_at')

    def get_author_name(self, comment):
        return comment.author.get_full_name() or comment.author.get_username()


class WorkOrderSerializer(serializers.ModelSerializer):
    assignee_name = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()
    assigned_to_me = serializers.SerializerMethodField()
    assignment_status = serializers.SerializerMethodField()
    assignment_responded_at = serializers.SerializerMethodField()
    assignment_decline_reason = serializers.SerializerMethodField()

    class Meta:
        model = WorkOrder
        fields = (
            'id', 'request', 'assignee', 'status', 'assigned_at', 'completed_at',
            'notes', 'assignee_name', 'assigned_to_me', 'created_at', 'updated_at',
            'assignment_status', 'assignment_responded_at', 'assignment_decline_reason',
        )
        read_only_fields = fields

    def get_assignee_name(self, work_order):
        if work_order.assignee_id is None:
            return None
        return work_order.assignee.get_full_name() or work_order.assignee.get_username()

    def get_notes(self, work_order):
        request = self.context.get('request')
        tenant = work_order.request.tenant
        if request and tenant and tenant.user_id == request.user.id:
            return ''
        return work_order.notes

    def get_assigned_to_me(self, work_order):
        request = self.context.get('request')
        return bool(request and work_order.assignee_id == request.user.pk)

    def _latest_assignment(self, work_order):
        return work_order.assignments.order_by('-created_at', '-pk').first()

    def get_assignment_status(self, work_order):
        assignment = self._latest_assignment(work_order)
        return assignment.status if assignment else None

    def get_assignment_responded_at(self, work_order):
        assignment = self._latest_assignment(work_order)
        return assignment.responded_at if assignment else None

    def get_assignment_decline_reason(self, work_order):
        request = self.context.get('request')
        tenant = work_order.request.tenant
        if request and tenant and tenant.user_id == request.user.id:
            return ''
        assignment = self._latest_assignment(work_order)
        return assignment.decline_reason if assignment else ''


class RepairQuotationSerializer(serializers.ModelSerializer):
    total_estimate_cents = serializers.IntegerField(read_only=True)
    decision_notes = serializers.SerializerMethodField()

    class Meta:
        model = RepairQuotation
        fields = (
            'id', 'work_order', 'labour_estimate_cents', 'materials_estimate_cents',
            'other_estimate_cents', 'total_estimate_cents', 'revision_of', 'explanation', 'status',
            'decision_at', 'decision_notes', 'created_at',
        )
        read_only_fields = fields

    def get_decision_notes(self, quotation):
        request = self.context.get('request')
        if request and quotation.work_order.request.tenant_id and quotation.work_order.request.tenant.user_id == request.user.id:
            return ''
        return quotation.decision_notes


class RepairMaterialUsedSerializer(serializers.ModelSerializer):
    unit_cost_cents = serializers.SerializerMethodField()

    class Meta:
        model = RepairMaterialUsed
        fields = ('id', 'description', 'quantity', 'unit', 'unit_cost_cents')
        read_only_fields = ('id',)

    def get_unit_cost_cents(self, material):
        request = self.context.get('request')
        tenant = material.completion.work_order.request.tenant
        if request and tenant and tenant.user_id == request.user.id:
            return None
        return material.unit_cost_cents


class RepairCompletionSerializer(serializers.ModelSerializer):
    materials = RepairMaterialUsedSerializer(many=True, read_only=True)
    actual_total_cents = serializers.SerializerMethodField()
    labour_cost_cents = serializers.SerializerMethodField()
    materials_cost_cents = serializers.SerializerMethodField()
    other_cost_cents = serializers.SerializerMethodField()
    verification_notes = serializers.SerializerMethodField()

    class Meta:
        model = RepairCompletion
        fields = (
            'id', 'diagnosis', 'failure_category', 'resolution_summary', 'outcome',
            'labour_cost_cents', 'materials_cost_cents', 'other_cost_cents',
            'actual_total_cents', 'submitted_at', 'status', 'verification_notes',
            'verified_at', 'follow_up_required', 'follow_up_reason', 'materials',
        )
        read_only_fields = fields

    def get_actual_total_cents(self, completion):
        if self._is_tenant(completion):
            return None
        return completion.labour_cost_cents + completion.materials_cost_cents + completion.other_cost_cents

    def _is_tenant(self, completion):
        request = self.context.get('request')
        tenant = completion.work_order.request.tenant
        return bool(request and tenant and tenant.user_id == request.user.id)

    def get_labour_cost_cents(self, completion):
        return None if self._is_tenant(completion) else completion.labour_cost_cents

    def get_materials_cost_cents(self, completion):
        return None if self._is_tenant(completion) else completion.materials_cost_cents

    def get_other_cost_cents(self, completion):
        return None if self._is_tenant(completion) else completion.other_cost_cents

    def get_verification_notes(self, completion):
        return '' if self._is_tenant(completion) else completion.verification_notes


class MaintenanceRequestSerializer(serializers.ModelSerializer):
    organization = serializers.IntegerField(source='organization_id', read_only=True)
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    property_name = serializers.CharField(source='unit.building.property.name', read_only=True)
    comments = MaintenanceCommentSerializer(many=True, read_only=True)
    work_order = serializers.SerializerMethodField()
    quotations = serializers.SerializerMethodField()
    completion = serializers.SerializerMethodField()
    triage_notes = serializers.SerializerMethodField()
    safety_override_reason = serializers.SerializerMethodField()
    follow_up_assignee_name = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceRequest
        fields = (
            'id', 'organization', 'unit', 'unit_name', 'property_name', 'tenant', 'created_by', 'title', 'description', 'category',
            'hazard', 'vulnerability', 'status', 'priority_class', 'score_millis',
            'emergency_override', 'safety_override', 'safety_override_reason', 'triage_notes',
            'triaged_at', 'requires_approval', 'follow_up_at', 'follow_up_reason',
            'follow_up_assignee_name', 'completed_at', 'closed_at', 'work_order',
            'quotations', 'completion', 'comments',
            'created_at', 'updated_at',
        )
        read_only_fields = fields

    def get_quotations(self, row):
        latest = row.work_order.quotations.all() if hasattr(row, 'work_order') else []
        request = self.context.get('request')
        if request and row.tenant_id and row.tenant.user_id == request.user.id:
            latest = latest.filter(status=RepairQuotation.Status.APPROVED)
        return RepairQuotationSerializer(latest, many=True, context=self.context).data

    def get_work_order(self, row):
        if not hasattr(row, 'work_order'):
            return None
        return WorkOrderSerializer(row.work_order, context=self.context).data

    def get_completion(self, row):
        if not hasattr(row, 'work_order'):
            return None
        completion = row.work_order.completions.order_by('-submitted_at', '-pk').first()
        if completion is None:
            return None
        return RepairCompletionSerializer(completion, context=self.context).data

    def _is_tenant(self, row):
        request = self.context.get('request')
        return bool(request and row.tenant_id and row.tenant.user_id == request.user.id)

    def get_triage_notes(self, row):
        return '' if self._is_tenant(row) else row.triage_notes

    def get_safety_override_reason(self, row):
        return '' if self._is_tenant(row) else row.safety_override_reason

    def get_follow_up_assignee_name(self, row):
        if self._is_tenant(row) or not row.follow_up_assignee_id:
            return None
        user = row.follow_up_assignee
        return user.get_full_name() or user.get_username()


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
    category = serializers.CharField(max_length=50, required=False, default='OTHER')
    requires_approval = serializers.BooleanField(required=False, default=False)
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


class TriageSerializer(serializers.Serializer):
    category = serializers.CharField(max_length=50)
    hazard = serializers.IntegerField(min_value=1, max_value=5)
    vulnerability = serializers.IntegerField(min_value=1, max_value=5)
    notes = serializers.CharField(required=False, allow_blank=True)
    safety_override = serializers.BooleanField(required=False, default=False)
    safety_override_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    requires_approval = serializers.BooleanField(required=False)


class QuotationWriteSerializer(serializers.Serializer):
    labour_estimate_cents = serializers.IntegerField(min_value=0)
    materials_estimate_cents = serializers.IntegerField(min_value=0)
    other_estimate_cents = serializers.IntegerField(min_value=0, required=False, default=0)
    explanation = serializers.CharField()

    def validate_explanation(self, value):
        if not value.strip():
            raise serializers.ValidationError('Explain the estimate and its assumptions.')
        return value


class QuotationDecisionSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
    notes = serializers.CharField(required=False, allow_blank=True)


class MaterialUsedWriteSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=200)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal('0.001'))
    unit = serializers.CharField(max_length=30)
    unit_cost_cents = serializers.IntegerField(min_value=0)


class CompletionWriteSerializer(serializers.Serializer):
    diagnosis = serializers.CharField()
    failure_category = serializers.CharField(max_length=50)
    resolution_summary = serializers.CharField()
    outcome = serializers.ChoiceField(choices=RepairCompletion.Outcome.choices)
    labour_cost_cents = serializers.IntegerField(min_value=0)
    materials_cost_cents = serializers.IntegerField(min_value=0)
    other_cost_cents = serializers.IntegerField(min_value=0, required=False, default=0)
    follow_up_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    materials = MaterialUsedWriteSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        for field in ('diagnosis', 'failure_category', 'resolution_summary'):
            if not attrs[field].strip():
                raise serializers.ValidationError({field: 'This field is required.'})
        if attrs['outcome'] == RepairCompletion.Outcome.NEEDS_FOLLOW_UP and not attrs.get('follow_up_reason', '').strip():
            raise serializers.ValidationError({'follow_up_reason': 'A reason is required for follow-up work.'})
        return attrs


class VerificationSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
    notes = serializers.CharField(required=False, allow_blank=True)


class AssignmentDeclineSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError('A decline reason is required.')
        return value


class FollowUpScheduleSerializer(serializers.Serializer):
    follow_up_at = serializers.DateTimeField()
    reason = serializers.CharField(max_length=500)
    assignee_id = serializers.IntegerField(min_value=1, required=False)

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError('A follow-up reason is required.')
        return value
