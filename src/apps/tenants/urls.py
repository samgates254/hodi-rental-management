from rest_framework.routers import DefaultRouter

from .views import TenantViewSet

app_name = 'tenants'

router = DefaultRouter()
router.register('', TenantViewSet, basename='tenant')

urlpatterns = router.urls
app_name = 'tenants'
