from django.urls import path

from .views import (
    AdminPaymentReversalView,
    AdminPaymentReviewView,
    AdminRevenueView,
    AdminEnterpriseInvoiceView,
    OrganizationSubscriptionView,
    PaymentReportView,
    PlanListView,
)

app_name = 'subscriptions'

urlpatterns = [
    path('plans/', PlanListView.as_view(), name='plans'),
    path('organization/', OrganizationSubscriptionView.as_view(), name='organization-subscription'),
    path('invoices/<uuid:invoice_id>/report-payment/', PaymentReportView.as_view(), name='report-payment'),
    path('admin/revenue/', AdminRevenueView.as_view(), name='admin-revenue'),
    path('admin/enterprise-invoices/', AdminEnterpriseInvoiceView.as_view(), name='admin-enterprise-invoice'),
    path('admin/payment-reports/', AdminPaymentReviewView.as_view(), name='admin-payment-reports'),
    path('admin/payment-reports/<int:attempt_id>/<str:action>/', AdminPaymentReviewView.as_view(), name='admin-payment-review'),
    path('admin/payments/<int:payment_id>/reverse/', AdminPaymentReversalView.as_view(), name='admin-payment-reversal'),
]
