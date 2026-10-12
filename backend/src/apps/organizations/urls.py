from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import (AccountantInvitationActionView, AccountantInvitationView,
	OrganizationMembershipViewSet, OrganizationStaffView, OrganizationViewSet)

app_name = 'organizations'

router = DefaultRouter()
router.register('memberships', OrganizationMembershipViewSet, basename='membership')
router.register('', OrganizationViewSet, basename='organization')

urlpatterns = [
	path('staff/', OrganizationStaffView.as_view(), name='staff'),
	path('accountant-invitations/', AccountantInvitationView.as_view(), name='accountant-invitations'),
	path('accountant-invitations/<int:invitation_id>/<str:action>/', AccountantInvitationActionView.as_view(), name='accountant-invitation-action'),
	*router.urls,
]
app_name = 'organizations'
