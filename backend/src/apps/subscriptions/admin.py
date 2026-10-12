from django.contrib import admin

from .models import (
    OrganizationSubscription,
    SubscriptionInvoice,
    SubscriptionPayment,
    SubscriptionPaymentAttempt,
    SubscriptionPlan,
)


class RetainedFinancialRecordAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'version', 'price_minor', 'currency', 'unit_limit', 'is_active')
    list_filter = ('is_active', 'is_custom_pricing')
    search_fields = ('name', 'code')
    actions = None
    list_editable = ('is_active',)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ('created_at', 'updated_at')
        return ('code', 'version', 'name', 'description', 'price_minor', 'currency', 'interval',
                'unit_limit', 'entitlements', 'is_custom_pricing', 'created_at', 'updated_at')

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrganizationSubscription)
class OrganizationSubscriptionAdmin(RetainedFinancialRecordAdmin):
    list_display = ('organization', 'plan', 'status', 'current_period_end')
    list_filter = ('status', 'plan')
    search_fields = ('organization__name',)
    readonly_fields = tuple(field.name for field in OrganizationSubscription._meta.fields)


@admin.register(SubscriptionInvoice)
class SubscriptionInvoiceAdmin(RetainedFinancialRecordAdmin):
    list_display = ('invoice_number', 'organization', 'plan', 'amount_minor', 'currency', 'status', 'due_date')
    list_filter = ('status', 'currency', 'plan')
    search_fields = ('invoice_number', 'organization__name')
    readonly_fields = tuple(field.name for field in SubscriptionInvoice._meta.fields)


@admin.register(SubscriptionPaymentAttempt)
class SubscriptionPaymentAttemptAdmin(RetainedFinancialRecordAdmin):
    list_display = ('invoice', 'organization', 'reference', 'status', 'reported_by', 'created_at')
    list_filter = ('status',)
    search_fields = ('reference', 'invoice__invoice_number', 'organization__name')
    readonly_fields = tuple(field.name for field in SubscriptionPaymentAttempt._meta.fields)


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(RetainedFinancialRecordAdmin):
    list_display = ('invoice', 'organization', 'amount_minor', 'currency', 'reference', 'status', 'confirmed_at')
    list_filter = ('status', 'currency')
    search_fields = ('reference', 'invoice__invoice_number', 'organization__name')
    readonly_fields = tuple(field.name for field in SubscriptionPayment._meta.fields)
