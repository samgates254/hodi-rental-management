from django.contrib import admin

from .models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'organization', 'user', 'phone_number', 'email', 'is_active')
    search_fields = ('first_name', 'last_name', 'phone_number', 'email', 'national_id', 'user__username')
    list_filter = ('is_active', 'organization')