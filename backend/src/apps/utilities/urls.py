from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import TenantUtilityView, UtilityAccountViewSet, UtilityBillViewSet

app_name = 'utilities'

router = DefaultRouter()
router.register('accounts', UtilityAccountViewSet, basename='utility-account')
router.register('bills', UtilityBillViewSet, basename='utility-bill')

urlpatterns = [path('me/', TenantUtilityView.as_view(), name='tenant-utilities'), *router.urls]
