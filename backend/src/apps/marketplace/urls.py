from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (CommerceListingViewSet, CommerceOrderViewSet, InquiryCreateView,
	ManagedListingViewSet, PublicListingViewSet, SupplierProfileViewSet)

app_name = 'marketplace'

router = DefaultRouter()
router.register('listings', PublicListingViewSet, basename='public-listing')
router.register('manage/listings', ManagedListingViewSet, basename='managed-listing')
router.register('commerce/listings', CommerceListingViewSet, basename='commerce-listing')
router.register('commerce/suppliers', SupplierProfileViewSet, basename='commerce-supplier')
router.register('commerce/orders', CommerceOrderViewSet, basename='commerce-order')

urlpatterns = [
	path('inquiries/', InquiryCreateView.as_view(), name='inquiry-create'),
	*router.urls,
]
