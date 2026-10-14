from django.urls import path

from .views import (
	LoginView,
<<<<<<< HEAD
	GoogleLoginView,
=======
	EmailVerificationConfirmView,
	EmailVerificationRequestView,
>>>>>>> 9c0db3f (feat: improve HODI marketplace and release readiness)
	LogoutView,
	MeView,
	OrganizationOptionsView,
	PasswordResetConfirmView,
	PasswordResetRequestView,
	SignupView,
	TenantOrganizationView,
)

app_name = 'accounts'

urlpatterns = [
	path('signup/', SignupView.as_view(), name='signup'),
	path('email-verification/request/', EmailVerificationRequestView.as_view(), name='email-verification-request'),
	path('verify-email/', EmailVerificationConfirmView.as_view(), name='email-verification-confirm'),
	path('organizations/', OrganizationOptionsView.as_view(), name='organization-options'),
	path('tenant-organization/', TenantOrganizationView.as_view(), name='tenant-organization'),
	path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset-request'),
	path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
	path('login/', LoginView.as_view(), name='login'),
	path('google/', GoogleLoginView.as_view(), name='google-login'),
	path('logout/', LogoutView.as_view(), name='logout'),
	path('me/', MeView.as_view(), name='me'),
]
