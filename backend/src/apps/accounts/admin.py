from django.contrib import admin

from .models import AccountProfile


@admin.register(AccountProfile)
class AccountProfileAdmin(admin.ModelAdmin):
	list_display = ('user', 'account_type', 'organization', 'professional_trade', 'phone_number', 'email_verified_at', 'created_at')
	list_filter = ('email_verified_at', 'created_at')
	search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name', 'phone_number')
	readonly_fields = ('email_verified_at', 'created_at', 'updated_at')