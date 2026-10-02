from django.urls import path
from rest_framework.routers import DefaultRouter

from .request_views import MaintenanceRequestViewSet, MatchPreviewView, WorkOrderViewSet
from .views import MaintenanceIssueViewSet

app_name = 'maintenance'

router = DefaultRouter()
router.register('issues', MaintenanceIssueViewSet, basename='issue')
router.register('requests', MaintenanceRequestViewSet, basename='request')
router.register('work-orders', WorkOrderViewSet, basename='work-order')

urlpatterns = [
	path('match/', MatchPreviewView.as_view(), name='match'),
	*router.urls,
]
