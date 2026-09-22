from rest_framework.routers import DefaultRouter

from .views import BuildingViewSet, PropertyViewSet, UnitViewSet

app_name = 'properties'

router = DefaultRouter()
router.register('buildings', BuildingViewSet, basename='building')
router.register('units', UnitViewSet, basename='unit')
router.register('', PropertyViewSet, basename='property')

urlpatterns = router.urls
app_name = 'properties'
