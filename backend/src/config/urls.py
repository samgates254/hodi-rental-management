from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health_check(request):
    return JsonResponse({'status': 'ok'})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/health/', health_check, name='health-check'),
    path('api/v1/accounts/', include('apps.accounts.urls')),
    path('api/v1/organizations/', include('apps.organizations.urls')),
    path('api/v1/properties/', include('apps.properties.urls')),
    path('api/v1/tenants/', include('apps.tenants.urls')),
    path('api/v1/leases/', include('apps.leases.urls')),
    path('api/v1/billing/', include('apps.billing.urls')),
    path('api/v1/maintenance/', include('apps.maintenance.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    path('api/v1/audit/', include('apps.audit.urls')),
    path('api/v1/marketplace/', include('apps.marketplace.urls')),
]
