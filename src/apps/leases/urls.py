from rest_framework.routers import DefaultRouter

from .views import LeaseAmendmentViewSet, LeaseViewSet, RentScheduleViewSet

app_name = 'leases'

router = DefaultRouter()
router.register('rent-schedules', RentScheduleViewSet, basename='rent-schedule')
router.register('amendments', LeaseAmendmentViewSet, basename='amendment')
router.register('', LeaseViewSet, basename='lease')

urlpatterns = router.urls
app_name = 'leases'

urlpatterns = []
