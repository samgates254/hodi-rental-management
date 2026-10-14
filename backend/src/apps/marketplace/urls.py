from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
	AgentAuthorizationView,
	AgentAuthorizedUnitsView,
	AgentInquiryViewSet,
	AgentListingViewSet,
	AgentProfileModerationView,
	AgentProfileView,
	AgentVerificationRequestView,
	AgentViewingRequestViewSet,
	CommerceListingViewSet,
	CommerceOrderViewSet,
	InquiryCreateView,
	ManagedListingViewSet,
	PublicListingViewSet,
	SupplierProfileViewSet,
)

app_name = 'marketplace'

router = DefaultRouter()
router.register('listings', PublicListingViewSet, basename='public-listing')
router.register('manage/listings', ManagedListingViewSet, basename='managed-listing')
router.register('agents/listings', AgentListingViewSet, basename='agent-listing')
router.register('agents/inquiries', AgentInquiryViewSet, basename='agent-inquiry')
router.register('agents/viewings', AgentViewingRequestViewSet, basename='agent-viewing')
router.register('commerce/listings', CommerceListingViewSet, basename='commerce-listing')
router.register('commerce/suppliers', SupplierProfileViewSet, basename='commerce-supplier')
router.register('commerce/orders', CommerceOrderViewSet, basename='commerce-order')

urlpatterns = [
	path('agents/me/', AgentProfileView.as_view(), name='agent-profile'),
	path('agents/me/authorized-units/', AgentAuthorizedUnitsView.as_view(), name='agent-authorized-units'),
	path('agents/me/request-verification/', AgentVerificationRequestView.as_view(), name='agent-verification-request'),
	path('agents/profiles/<int:profile_id>/moderate/', AgentProfileModerationView.as_view(), name='agent-profile-moderate'),
	path('agent-authorizations/', AgentAuthorizationView.as_view(), name='agent-authorization-list-create'),
	path('agent-authorizations/<int:authorization_id>/', AgentAuthorizationView.as_view(), name='agent-authorization-detail'),
	path('inquiries/', InquiryCreateView.as_view(), name='inquiry-create'),
	*router.urls,
]
