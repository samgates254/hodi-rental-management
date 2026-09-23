from django.contrib import admin

from .models import Lease, LeaseAmendment, RentSchedule


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = ('reference', 'tenant', 'unit', 'start_date', 'end_date', 'status', 'monthly_rent_minor')
    search_fields = ('reference', 'tenant__first_name', 'tenant__last_name', 'unit__name')
    list_filter = ('status',)


@admin.register(RentSchedule)
class RentScheduleAdmin(admin.ModelAdmin):
    list_display = ('lease', 'effective_from', 'effective_to', 'amount_minor', 'frequency')
    list_filter = ('frequency',)


@admin.register(LeaseAmendment)
class LeaseAmendmentAdmin(admin.ModelAdmin):
    list_display = ('lease', 'amendment_type', 'effective_date', 'created_by', 'created_at')
    list_filter = ('amendment_type',)
    search_fields = ('lease__reference', 'reason', 'created_by__username')