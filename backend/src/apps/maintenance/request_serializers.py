from rest_framework import serializers
from decimal import Decimal

from apps.properties.models import Unit
from apps.organizations.models import OrganizationMembership
from apps.tenants.models import Tenant
from apps.marketplace.models import SupplierProfile

from .models import (
    JobMaterialPurchase, JobMaterialReceipt, MaintenanceComment, MaintenanceRequest,
    RepairCompletion, RepairCompletionEvidence, RepairMaterialUsed, RepairQuotation,
    RepairQuotationLine, TurnoverAssessment, TurnoverChecklistItem, WorkOrder,
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
    lines = serializers.SerializerMethodField()
    has_itemized_lines = serializers.SerializerMethodField()

    class Meta:
        model = RepairQuotation
        fields = (
            'id', 'work_order', 'labour_estimate_cents', 'materials_estimate_cents',
            'other_estimate_cents', 'total_estimate_cents', 'revision_of', 'explanation', 'status',
            'decision_at', 'decision_notes', 'created_at', 'lines', 'has_itemized_lines',
        )
        read_only_fields = fields

    def get_decision_notes(self, quotation):
        request = self.context.get('request')
        if request and quotation.work_order.request.tenant_id and quotation.work_order.request.tenant.user_id == request.user.id:
            return ''
        return quotation.decision_notes

    def get_lines(self, quotation):
        return RepairQuotationLineSerializer(quotation.lines.all(), many=True).data

    def get_has_itemized_lines(self, quotation):
        return quotation.lines.exists()


class RepairQuotationLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepairQuotationLine
        fields = ('id', 'category', 'description', 'quantity', 'unit', 'unit_price_cents', 'line_total_cents', 'created_at')
        read_only_fields = fields


class RepairMaterialUsedSerializer(serializers.ModelSerializer):
    unit_cost_cents = serializers.SerializerMethodField()
    purchase = serializers.SerializerMethodField()

    class Meta:
        model = RepairMaterialUsed
        fields = ('id', 'description', 'quantity', 'unit', 'unit_cost_cents', 'purchase')
        read_only_fields = ('id',)

    def get_unit_cost_cents(self, material):
        request = self.context.get('request')
        tenant = material.completion.work_order.request.tenant
        if request and tenant and tenant.user_id == request.user.id:
            return None
        return material.unit_cost_cents

    def get_purchase(self, material):
        request = self.context.get('request')
        tenant = material.completion.work_order.request.tenant
        if request and tenant and tenant.user_id == request.user.id:
            return None
        return material.purchase_id


class JobMaterialReceiptSerializer(serializers.ModelSerializer):
    acknowledged_by_name = serializers.SerializerMethodField()

    class Meta:
        model = JobMaterialReceipt
        fields = ('id', 'quantity', 'evidence_reference', 'notes', 'acknowledged_by', 'acknowledged_by_name', 'created_at')
        read_only_fields = fields

    def get_acknowledged_by_name(self, receipt):
        return receipt.acknowledged_by.get_full_name() or receipt.acknowledged_by.get_username()


class JobMaterialPurchaseSerializer(serializers.ModelSerializer):
    received_quantity = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    unit_price_cents = serializers.SerializerMethodField()
    purchase_total_cents = serializers.SerializerMethodField()
    overrun_reason = serializers.SerializerMethodField()
    overrun_authorized_by = serializers.SerializerMethodField()
    overrun_authorized_by_name = serializers.SerializerMethodField()
    can_acknowledge_receipt = serializers.SerializerMethodField()
    supplier_name = serializers.SerializerMethodField()
    supplier_reference = serializers.SerializerMethodField()
    receipts = serializers.SerializerMethodField()

    class Meta:
        model = JobMaterialPurchase
        fields = (
            'id', 'organization', 'maintenance_request', 'quotation', 'quotation_line',
            'supplier_name', 'supplier_reference', 'description', 'quantity', 'received_quantity',
            'supplier_profile',
            'unit', 'unit_price_cents', 'purchase_total_cents', 'purchase_date', 'status',
            'receipt_count', 'receipts', 'overrun_reason', 'overrun_authorized_by',
            'overrun_authorized_by_name', 'overrun_authorized_at', 'created_by', 'created_by_name', 'created_at',
            'can_acknowledge_receipt',
        )
        read_only_fields = fields

    receipt_count = serializers.SerializerMethodField()

    def get_received_quantity(self, purchase):
        return str(sum((receipt.quantity for receipt in purchase.receipts.all()), Decimal('0')))

    def _can_view_costs(self, purchase):
        request = self.context.get('request')
        return bool(request and OrganizationMembership.objects.filter(
            user=request.user, organization_id=purchase.organization_id,
            organization__is_active=True, is_active=True,
            role__in=(OrganizationMembership.Role.OWNER, OrganizationMembership.Role.PROPERTY_MANAGER),
        ).exists())

    def _is_assigned_technician(self, purchase):
        request = self.context.get('request')
        return bool(request and WorkOrder.objects.filter(
            request_id=purchase.maintenance_request_id, assignee=request.user,
        ).exists())

    def get_can_acknowledge_receipt(self, purchase):
        request = self.context.get('request')
        return bool(request and purchase.created_by_id != request.user.id and OrganizationMembership.objects.filter(
            user=request.user, organization_id=purchase.organization_id,
            organization__is_active=True, is_active=True,
            role__in=(OrganizationMembership.Role.OWNER, OrganizationMembership.Role.PROPERTY_MANAGER,
                      OrganizationMembership.Role.CARETAKER),
        ).exists())

    def get_supplier_name(self, purchase):
        return '' if self._is_assigned_technician(purchase) else purchase.supplier_name

    def get_supplier_reference(self, purchase):
        return '' if self._is_assigned_technician(purchase) else purchase.supplier_reference

    def get_receipts(self, purchase):
        if self._is_assigned_technician(purchase):
            return []
        return JobMaterialReceiptSerializer(purchase.receipts.all(), many=True).data

    def get_unit_price_cents(self, purchase):
        return purchase.unit_price_cents if self._can_view_costs(purchase) else None

    def get_purchase_total_cents(self, purchase):
        return purchase.purchase_total_cents if self._can_view_costs(purchase) else None

    def get_overrun_reason(self, purchase):
        return purchase.overrun_reason if self._can_view_costs(purchase) else ''

    def get_overrun_authorized_by(self, purchase):
        return purchase.overrun_authorized_by_id if self._can_view_costs(purchase) else None

    def get_receipt_count(self, purchase):
        return purchase.receipts.count()

    def get_created_by_name(self, purchase):
        if self._is_assigned_technician(purchase):
            return ''
        return purchase.created_by.get_full_name() or purchase.created_by.get_username()

    def get_overrun_authorized_by_name(self, purchase):
        if not purchase.overrun_authorized_by_id or not self._can_view_costs(purchase):
            return None
        user = purchase.overrun_authorized_by
        return user.get_full_name() or user.get_username()


class RepairCompletionSerializer(serializers.ModelSerializer):
    materials = RepairMaterialUsedSerializer(many=True, read_only=True)
    actual_total_cents = serializers.SerializerMethodField()
    labour_cost_cents = serializers.SerializerMethodField()
    materials_cost_cents = serializers.SerializerMethodField()
    other_cost_cents = serializers.SerializerMethodField()
    verification_notes = serializers.SerializerMethodField()
    verified_by_name = serializers.SerializerMethodField()
    cost_overrun_reason = serializers.SerializerMethodField()
    cost_overrun_authorized_by_name = serializers.SerializerMethodField()
    can_add_evidence = serializers.SerializerMethodField()

    class Meta:
        model = RepairCompletion
        fields = (
            'id', 'diagnosis', 'failure_category', 'resolution_summary', 'outcome',
            'labour_cost_cents', 'materials_cost_cents', 'other_cost_cents',
            'actual_total_cents', 'submitted_at', 'status', 'verification_notes',
            'verified_at', 'verified_by_name', 'follow_up_required', 'follow_up_reason', 'materials',
            'cost_overrun_reason', 'cost_overrun_authorized_by_name', 'cost_overrun_authorized_at',
            'can_add_evidence',
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

    def get_verified_by_name(self, completion):
        if self._is_tenant(completion) or not completion.verified_by_id:
            return None
        return completion.verified_by.get_full_name() or completion.verified_by.get_username()

    def get_cost_overrun_reason(self, completion):
        return '' if self._is_tenant(completion) else completion.cost_overrun_reason

    def get_cost_overrun_authorized_by_name(self, completion):
        if self._is_tenant(completion) or not completion.cost_overrun_authorized_by_id:
            return None
        user = completion.cost_overrun_authorized_by
        return user.get_full_name() or user.get_username()

    def get_can_add_evidence(self, completion):
        request = self.context.get('request')
        return bool(request and completion.submitted_by_id == request.user.id and completion.status == RepairCompletion.Status.SUBMITTED)


class RepairCompletionEvidenceSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = RepairCompletionEvidence
        fields = (
            'id', 'organization', 'maintenance_request', 'completion', 'category', 'caption',
            'evidence_reference', 'recorded_by', 'recorded_by_name', 'created_at',
        )
        read_only_fields = fields

    def get_recorded_by_name(self, evidence):
        return evidence.recorded_by.get_full_name() or evidence.recorded_by.get_username()


class CompletionEvidenceWriteSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=RepairCompletionEvidence.Category.choices)
    caption = serializers.CharField(max_length=240, required=False, allow_blank=True, default='')
    evidence_reference = serializers.CharField(max_length=500)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: 'Unknown evidence field.' for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate_evidence_reference(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Provide a private evidence reference.')
        if value.lower().startswith(('http://', 'https://')):
            raise serializers.ValidationError('Public URLs cannot be used as private evidence storage references.')
        return value


class TurnoverAssessmentCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: 'Unit, building and organization are derived from the repair job.' for key in sorted(unknown)})
        return super().to_internal_value(data)


class TurnoverChecklistItemWriteSerializer(serializers.Serializer):
    item_key = serializers.SlugField(max_length=50)
    label = serializers.CharField(max_length=160)
    passed = serializers.BooleanField()
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: 'Unknown checklist field.' for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate(self, attrs):
        for field in ('item_key', 'label', 'notes'):
            attrs[field] = attrs[field].strip()
        if not attrs['item_key'] or not attrs['label']:
            raise serializers.ValidationError('Each checklist item needs a key and label.')
        return attrs


class TurnoverAssessmentDecisionSerializer(serializers.Serializer):
    ready = serializers.BooleanField()
    outstanding_issues = serializers.CharField(required=False, allow_blank=True, max_length=5000, default='')
    checklist_items = TurnoverChecklistItemWriteSerializer(many=True, allow_empty=False, max_length=30)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: 'Unknown assessment field.' for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate(self, attrs):
        keys = [item['item_key'] for item in attrs['checklist_items']]
        if len(keys) != len(set(keys)):
            raise serializers.ValidationError({'checklist_items': 'Checklist item keys must be unique.'})
        attrs['outstanding_issues'] = attrs['outstanding_issues'].strip()
        return attrs


class TurnoverChecklistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TurnoverChecklistItem
        fields = ('id', 'item_key', 'label', 'passed', 'notes')
        read_only_fields = fields


class TurnoverAssessmentSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    building_name = serializers.CharField(source='building.name', read_only=True)
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    requested_by_name = serializers.SerializerMethodField()
    assessed_by_name = serializers.SerializerMethodField()
    checklist_items = TurnoverChecklistItemSerializer(many=True, read_only=True)

    class Meta:
        model = TurnoverAssessment
        fields = (
            'id', 'organization', 'property', 'property_name', 'building', 'building_name', 'unit', 'unit_name',
            'maintenance_request', 'revision_of', 'status', 'outstanding_issues', 'requested_by',
            'requested_by_name', 'requested_at', 'assessed_by', 'assessed_by_name', 'assessed_at', 'checklist_items',
        )
        read_only_fields = fields

    def get_requested_by_name(self, assessment):
        return assessment.requested_by.get_full_name() or assessment.requested_by.get_username()

    def get_assessed_by_name(self, assessment):
        if not assessment.assessed_by_id:
            return None
        return assessment.assessed_by.get_full_name() or assessment.assessed_by.get_username()


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
    labour_estimate_cents = serializers.IntegerField(min_value=0, required=False)
    materials_estimate_cents = serializers.IntegerField(min_value=0, required=False)
    other_estimate_cents = serializers.IntegerField(min_value=0, required=False)
    total_estimate_cents = serializers.IntegerField(min_value=0, required=False)
    lines = serializers.ListField(child=serializers.DictField(), required=False, allow_empty=False, max_length=100)
    explanation = serializers.CharField()

    def to_internal_value(self, data):
        allowed = set(self.fields)
        if isinstance(data, dict):
            unknown = set(data) - allowed
            if unknown:
                raise serializers.ValidationError({key: 'Unknown quotation field.' for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate_explanation(self, value):
        if not value.strip():
            raise serializers.ValidationError('Explain the estimate and its assumptions.')
        return value

    def validate(self, attrs):
        from application.services.maintenance import _itemized_totals

        lines = attrs.get('lines')
        if lines is None:
            if 'labour_estimate_cents' not in attrs or 'materials_estimate_cents' not in attrs:
                raise serializers.ValidationError('Provide legacy category totals or itemized quotation lines.')
            attrs.setdefault('other_estimate_cents', 0)
            if attrs.get('total_estimate_cents') is not None:
                total = sum(attrs[key] for key in ('labour_estimate_cents', 'materials_estimate_cents', 'other_estimate_cents'))
                if attrs['total_estimate_cents'] != total:
                    raise serializers.ValidationError({'total_estimate_cents': 'Total must equal the category totals.'})
            attrs['itemized'] = False
            return attrs

        parsed = []
        line_serializer = QuotationLineWriteSerializer(data=lines, many=True)
        line_serializer.is_valid(raise_exception=True)
        parsed = line_serializer.validated_data
        _, totals = _itemized_totals(parsed)
        for field in ('labour_estimate_cents', 'materials_estimate_cents', 'other_estimate_cents'):
            if field in attrs and attrs[field] != totals[field]:
                raise serializers.ValidationError({field: 'This subtotal must match the itemized lines.'})
        expected_total = sum(totals.values())
        if 'total_estimate_cents' in attrs and attrs['total_estimate_cents'] != expected_total:
            raise serializers.ValidationError({'total_estimate_cents': 'Total must match the itemized lines.'})
        attrs['lines'] = parsed
        attrs['itemized'] = True
        return attrs


class QuotationLineWriteSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=RepairQuotationLine.Category.choices)
    description = serializers.CharField(max_length=240, allow_blank=False)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal('0.001'))
    unit = serializers.CharField(max_length=30, allow_blank=False)
    unit_price_cents = serializers.IntegerField(min_value=0, max_value=9223372036854775807)
    line_total_cents = serializers.IntegerField(min_value=0, required=False)

    def to_internal_value(self, data):
        allowed = set(self.fields)
        if isinstance(data, dict):
            unknown = set(data) - allowed
            if unknown:
                raise serializers.ValidationError({key: 'Unknown quotation line field.' for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate(self, attrs):
        from application.services.maintenance import quotation_line_total_cents

        for field in ('description', 'unit'):
            attrs[field] = attrs[field].strip()
            if not attrs[field]:
                raise serializers.ValidationError({field: 'This field cannot be blank.'})
        expected = quotation_line_total_cents(attrs['quantity'], attrs['unit_price_cents'])
        if 'line_total_cents' in attrs and attrs['line_total_cents'] != expected:
            raise serializers.ValidationError({'line_total_cents': 'Line total must match quantity and unit price.'})
        attrs.pop('line_total_cents', None)
        return attrs


class QuotationDecisionSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
    notes = serializers.CharField(required=False, allow_blank=True)


class MaterialUsedWriteSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=200)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal('0.001'))
    unit = serializers.CharField(max_length=30)
    unit_cost_cents = serializers.IntegerField(min_value=0)
    purchase_id = serializers.IntegerField(min_value=1, required=False)


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
    authorize_cost_overrun = serializers.BooleanField(required=False, default=False)
    cost_overrun_reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs):
        reason = attrs.get('cost_overrun_reason', '').strip()
        if attrs.get('authorize_cost_overrun') and not reason:
            raise serializers.ValidationError({'cost_overrun_reason': 'A reason is required to authorize a cost overrun.'})
        if reason and not attrs.get('authorize_cost_overrun'):
            raise serializers.ValidationError({'authorize_cost_overrun': 'Confirm the cost overrun authorization.'})
        attrs['cost_overrun_reason'] = reason
        return attrs


class MaterialPurchaseWriteSerializer(serializers.Serializer):
    quotation_id = serializers.IntegerField(min_value=1)
    quotation_line_id = serializers.IntegerField(min_value=1)
    supplier_name = serializers.CharField(max_length=200)
    supplier_profile = serializers.PrimaryKeyRelatedField(queryset=SupplierProfile.objects.filter(is_active=True), required=False, allow_null=True)
    supplier_reference = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal('0.001'))
    unit_price_cents = serializers.IntegerField(min_value=0, max_value=9223372036854775807)
    purchase_date = serializers.DateField()
    idempotency_key = serializers.UUIDField()
    overrun_reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs):
        attrs['supplier_name'] = attrs['supplier_name'].strip()
        attrs['supplier_reference'] = attrs['supplier_reference'].strip()
        attrs['overrun_reason'] = attrs.get('overrun_reason', '').strip()
        if not attrs['supplier_name']:
            raise serializers.ValidationError({'supplier_name': 'Supplier name is required.'})
        return attrs


class MaterialReceiptWriteSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal('0.001'))
    evidence_reference = serializers.CharField(max_length=500)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')
    idempotency_key = serializers.UUIDField()

    def validate(self, attrs):
        attrs['evidence_reference'] = attrs['evidence_reference'].strip()
        attrs['notes'] = attrs['notes'].strip()
        if not attrs['evidence_reference']:
            raise serializers.ValidationError({'evidence_reference': 'Provide a receipt or delivery evidence reference.'})
        return attrs


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
