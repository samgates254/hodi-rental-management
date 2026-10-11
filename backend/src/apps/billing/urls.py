from django.urls import path
from rest_framework.routers import DefaultRouter

from .statement_views import MyStatementPdfView, MyStatementView
from .views import RentPaymentViewSet
from .views_ledger import ChargeViewSet, DelinquencyView, InvoiceViewSet, PaymentViewSet
from .views_mpesa import MpesaAttemptStatusView, MpesaCallbackView, MpesaInitiateView

app_name = 'billing'

router = DefaultRouter()
router.register('payments', RentPaymentViewSet, basename='payment')
router.register('invoices', InvoiceViewSet, basename='invoice')
router.register('charges', ChargeViewSet, basename='charge')
router.register('ledger-payments', PaymentViewSet, basename='ledger-payment')

urlpatterns = [
	path('statements/me/', MyStatementView.as_view(), name='statement-me'),
	path('statements/me/pdf/', MyStatementPdfView.as_view(), name='statement-me-pdf'),
	path('delinquency/', DelinquencyView.as_view(), name='delinquency'),
	path('mpesa/initiate/', MpesaInitiateView.as_view(), name='mpesa-initiate'),
	path('mpesa/attempts/<uuid:attempt_id>/', MpesaAttemptStatusView.as_view(), name='mpesa-attempt-status'),
	path('mpesa/callback/', MpesaCallbackView.as_view(), name='mpesa-callback'),
	path(
		'mpesa/callback/<str:callback_token>/',
		MpesaCallbackView.as_view(),
		name='mpesa-callback-token',
	),

	*router.urls,
]
