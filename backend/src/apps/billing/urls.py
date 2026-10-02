from rest_framework.routers import DefaultRouter

from .views import RentPaymentViewSet

app_name = 'billing'

router = DefaultRouter()
router.register('payments', RentPaymentViewSet, basename='payment')

urlpatterns = router.urls
