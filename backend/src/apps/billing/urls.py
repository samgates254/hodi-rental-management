from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import RentPaymentViewSet
from .views_ledger import ChargeViewSet, DelinquencyView, InvoiceViewSet, PaymentViewSet

app_name = 'billing'

router = DefaultRouter()
router.register('payments', RentPaymentViewSet, basename='payment')
router.register('invoices', InvoiceViewSet, basename='invoice')
router.register('charges', ChargeViewSet, basename='charge')
router.register('ledger-payments', PaymentViewSet, basename='ledger-payment')

urlpatterns = [
	path('delinquency/', DelinquencyView.as_view(), name='delinquency'),
	*router.urls,
]
