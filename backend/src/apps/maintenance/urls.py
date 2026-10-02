from rest_framework.routers import DefaultRouter

from .views import MaintenanceIssueViewSet

app_name = 'maintenance'

router = DefaultRouter()
router.register('issues', MaintenanceIssueViewSet, basename='issue')

urlpatterns = router.urls
