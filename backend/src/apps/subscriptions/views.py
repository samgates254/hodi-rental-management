from datetime import date

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import OrganizationMembership
from application.services.audit import record_audit

from .models import (
    OrganizationSubscription,
    SubscriptionInvoice,
    SubscriptionPayment,
    SubscriptionPaymentAttempt,
    SubscriptionPlan,
)
from .serializers import (
    OrganizationSubscriptionSerializer,
    EnterpriseInvoiceSerializer,
    PaymentReportSerializer,
    PaymentReviewSerializer,
    PlanChangeSerializer,
    PublicSubscriptionPlanSerializer,
    SubscriptionPaymentAttemptSerializer,
    SubscriptionPlanSerializer,
)
from .services import (
    confirm_reported_payment,
    get_or_create_free_subscription,
    issue_enterprise_invoice,
    rentable_unit_count,
    reject_reported_payment,
    report_payment,
    request_plan_change,
    reverse_subscription_payment,
)


SUBSCRIPTION_READ_ROLES = (
    OrganizationMembership.Role.OWNER,
    OrganizationMembership.Role.PROPERTY_MANAGER,
    OrganizationMembership.Role.ACCOUNTANT,
)
SUBSCRIPTION_WRITE_ROLES = (
    OrganizationMembership.Role.OWNER,
    OrganizationMembership.Role.PROPERTY_MANAGER,
)


def _membership(user, organization_id, roles):
    membership = OrganizationMembership.objects.filter(
        organization_id=organization_id, user=user, is_active=True,
        organization__is_active=True, role__in=roles,
    ).select_related('organization').first()
    if membership is None:
        raise NotFound('Organization not found.')
    return membership


class PlanListView(APIView):
    # Public plan discovery contains no organization, invoice, or payment data.
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price_minor', 'name')
        return Response(PublicSubscriptionPlanSerializer(plans, many=True).data)


class OrganizationSubscriptionView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        organization_id = request.query_params.get('organization')
        membership = _membership(request.user, organization_id, SUBSCRIPTION_READ_ROLES)
        subscription = get_or_create_free_subscription(membership.organization)
        units = rentable_unit_count(membership.organization_id)
        limit = subscription.effective_unit_limit
        from .serializers import OrganizationSubscriptionSerializer, SubscriptionInvoiceSerializer
        return Response({
            'id': subscription.pk,
            'organization': membership.organization_id,
            'plan': SubscriptionPlanSerializer(subscription.plan).data,
            'pending_plan': SubscriptionPlanSerializer(subscription.pending_plan).data if subscription.pending_plan_id else None,
            'status': subscription.status,
            'current_period_start': subscription.current_period_start,
            'current_period_end': subscription.current_period_end,
            'unit_limit_override': subscription.unit_limit_override,
            'setup_fee_paid': subscription.setup_fee_paid,
            'setup_fee_invoiced': subscription.setup_fee_invoiced,
            'effective_unit_limit': limit,
            'unit_count': units,
            'remaining_units': None if limit is None else max(0, limit - units),
            'effective_entitlements': subscription.effective_entitlements,
            'invoices': SubscriptionInvoiceSerializer(
                subscription.invoices.select_related('plan', 'payment').prefetch_related('payment_attempts')[:50], many=True,
            ).data,
        })

    def post(self, request):
        serializer = PlanChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization_id = request.data.get('organization')
        membership = _membership(request.user, organization_id, SUBSCRIPTION_WRITE_ROLES)
        invoice = request_plan_change(
            organization_id=membership.organization_id,
            plan_code=serializer.validated_data['plan'], actor=request.user, request=request,
        )
        from .serializers import SubscriptionInvoiceSerializer
        return Response(SubscriptionInvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


class PaymentReportView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, invoice_id):
        serializer = PaymentReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = SubscriptionInvoice.objects.filter(pk=invoice_id).first()
        if invoice is None:
            raise NotFound('Subscription invoice not found.')
        _membership(request.user, invoice.organization_id, SUBSCRIPTION_WRITE_ROLES)
        attempt = report_payment(
            invoice_id=invoice.pk, organization_id=invoice.organization_id, actor=request.user,
            reference=serializer.validated_data['reference'], request=request,
        )
        return Response(SubscriptionPaymentAttemptSerializer(attempt).data, status=status.HTTP_202_ACCEPTED)


class HodiAdminOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class AdminRevenueView(APIView):
    permission_classes = (HodiAdminOnly,)

    def get(self, request):
        today = timezone.localdate()
        payments = SubscriptionPayment.objects.all()
        settled = payments.filter(status=SubscriptionPayment.Status.VERIFIED)
        invoices = SubscriptionInvoice.objects.all()
        plan_counts = list(OrganizationSubscription.objects.values(
            'plan__code', 'plan__name', 'status',
        ).annotate(organizations=Count('id')).order_by('plan__name', 'status'))
        from apps.audit.models import AuditLog
        revenue_actions = (
            'subscription.plan_change_requested', 'subscription.payment_reported',
            'subscription.payment_verified', 'subscription.payment_report_rejected',
            'subscription.payment_reversed',
        )
        activity = AuditLog.objects.filter(action__in=revenue_actions).select_related(
            'actor', 'organization',
        ).order_by('-created_at')[:30]
        activity_data = [{
            'action': row.action, 'object_type': row.object_type, 'object_id': row.object_id,
            'organization': row.organization.name if row.organization else None,
            'actor': row.actor.get_username() if row.actor else None,
            'created_at': row.created_at,
        } for row in activity]
        successful_changes = AuditLog.objects.filter(action='subscription.payment_verified')
        collected_minor = payments.aggregate(value=Sum('amount_minor'))['value'] or 0
        reversed_minor = payments.filter(status=SubscriptionPayment.Status.REVERSED).aggregate(value=Sum('amount_minor'))['value'] or 0
        setup_fees_collected = settled.aggregate(value=Sum('invoice__setup_fee_minor'))['value'] or 0
        monthly_fees_collected = settled.aggregate(value=Sum('invoice__monthly_fee_minor'))['value'] or 0
        setup_fees_reversed = payments.filter(status=SubscriptionPayment.Status.REVERSED).aggregate(value=Sum('invoice__setup_fee_minor'))['value'] or 0
        monthly_fees_reversed = payments.filter(status=SubscriptionPayment.Status.REVERSED).aggregate(value=Sum('invoice__monthly_fee_minor'))['value'] or 0
        return Response({
            'active_subscriptions': OrganizationSubscription.objects.filter(status=OrganizationSubscription.Status.ACTIVE).count(),
            'free_organizations': OrganizationSubscription.objects.filter(status=OrganizationSubscription.Status.FREE).count(),
            'organizations_by_plan': plan_counts,
            'subscription_invoices_issued': invoices.count(),
            'verified_payments': settled.count(),
            'collected_minor': collected_minor,
            'reversed_minor': reversed_minor,
            'net_collected_minor': collected_minor - reversed_minor,
            'setup_fees_collected_minor': setup_fees_collected,
            'monthly_fees_collected_minor': monthly_fees_collected,
            'setup_fees_reversed_minor': setup_fees_reversed,
            'monthly_fees_reversed_minor': monthly_fees_reversed,
            'outstanding_minor': invoices.filter(status__in=(SubscriptionInvoice.Status.ISSUED, SubscriptionInvoice.Status.OVERDUE)).aggregate(value=Sum('amount_minor'))['value'] or 0,
            'overdue_invoices': invoices.filter(Q(status=SubscriptionInvoice.Status.OVERDUE) | Q(status=SubscriptionInvoice.Status.ISSUED, due_date__lt=today)).count(),
            'cancelled_or_expired': OrganizationSubscription.objects.filter(status__in=(OrganizationSubscription.Status.CANCELLED, OrganizationSubscription.Status.EXPIRED)).count(),
            'paid_organizations': OrganizationSubscription.objects.filter(status=OrganizationSubscription.Status.ACTIVE).exclude(plan__code='free').count(),
            'verified_plan_upgrades': successful_changes.filter(metadata__change_direction='upgrade').count(),
            'verified_plan_downgrades': successful_changes.filter(metadata__change_direction='downgrade').count(),
            'pending_payment_reports': SubscriptionPaymentAttempt.objects.filter(status=SubscriptionPaymentAttempt.Status.PENDING_REVIEW).count(),
            'recent_activity': activity_data,
        })


class AdminPaymentReviewView(APIView):
    permission_classes = (HodiAdminOnly,)

    def get(self, request):
        attempts = SubscriptionPaymentAttempt.objects.filter(
            status=SubscriptionPaymentAttempt.Status.PENDING_REVIEW,
        ).select_related('invoice', 'organization', 'reported_by').order_by('created_at')
        return Response(SubscriptionPaymentAttemptSerializer(attempts, many=True).data)

    def post(self, request, attempt_id, action):
        serializer = PaymentReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['reason']
        if action == 'confirm':
            payment = confirm_reported_payment(
                attempt_id=attempt_id, actor=request.user, reason=reason, request=request,
            )
            return Response({'status': payment.status, 'reference': payment.reference})
        if action == 'reject':
            attempt = reject_reported_payment(
                attempt_id=attempt_id, actor=request.user, reason=reason, request=request,
            )
            return Response({'status': attempt.status})
        raise NotFound('Unknown payment review action.')


class AdminPaymentReversalView(APIView):
    permission_classes = (HodiAdminOnly,)

    def post(self, request, payment_id):
        serializer = PaymentReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = reverse_subscription_payment(
            payment_id=payment_id, actor=request.user,
            reason=serializer.validated_data['reason'], request=request,
        )
        return Response({'status': payment.status})


class AdminEnterpriseInvoiceView(APIView):
    permission_classes = (HodiAdminOnly,)

    def get(self, request):
        subscriptions = OrganizationSubscription.objects.select_related('organization', 'plan').order_by('organization__name')
        return Response([{
            'organization': row.organization_id,
            'organization_name': row.organization.name,
            'current_plan': row.plan.name,
            'status': row.status,
        } for row in subscriptions])

    def post(self, request):
        serializer = EnterpriseInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            OrganizationSubscription.objects.get(organization_id=values['organization'])
        except OrganizationSubscription.DoesNotExist as error:
            raise NotFound('Organization subscription not found.') from error
        invoice = issue_enterprise_invoice(
            organization_id=values['organization'], amount_minor=values['amount_minor'],
            unit_limit=values['unit_limit'], actor=request.user, reason=values['reason'], request=request,
        )
        from .serializers import SubscriptionInvoiceSerializer
        return Response(SubscriptionInvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)

