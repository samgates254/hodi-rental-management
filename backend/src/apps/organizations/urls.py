from rest_framework.routers import DefaultRouter

from .views import OrganizationMembershipViewSet, OrganizationViewSet

app_name = 'organizations'

router = DefaultRouter()
router.register('memberships', OrganizationMembershipViewSet, basename='membership')
router.register('', OrganizationViewSet, basename='organization')

urlpatterns = router.urls
app_name = 'organizations'
