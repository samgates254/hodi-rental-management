from django.contrib import admin

from .models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'organization', 'phone_number', 'email', 'is_active')
    search_fields = ('first_name', 'last_name', 'phone_number', 'email', 'national_id')
    list_filter = ('is_active', 'organization')