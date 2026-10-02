from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import InquiryCreateView, ManagedListingViewSet, PublicListingViewSet

app_name = 'marketplace'

router = DefaultRouter()
router.register('listings', PublicListingViewSet, basename='public-listing')
router.register('manage/listings', ManagedListingViewSet, basename='managed-listing')

urlpatterns = [
	path('inquiries/', InquiryCreateView.as_view(), name='inquiry-create'),
	*router.urls,
]
