from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import OrganizationMembershipViewSet, OrganizationStaffView, OrganizationViewSet

app_name = 'organizations'

router = DefaultRouter()
router.register('memberships', OrganizationMembershipViewSet, basename='membership')
router.register('', OrganizationViewSet, basename='organization')

urlpatterns = [
	path('staff/', OrganizationStaffView.as_view(), name='staff'),
	*router.urls,
]
app_name = 'organizations'
