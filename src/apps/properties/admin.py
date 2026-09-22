from django.contrib import admin

from .models import Building, Property, Unit


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'city', 'country', 'is_active')
    search_fields = ('name', 'organization__name', 'city')
    list_filter = ('is_active', 'country')


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('name', 'property', 'created_at')
    search_fields = ('name', 'property__name')


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'building', 'status', 'bedrooms')
    search_fields = ('name', 'building__name', 'building__property__name')
    list_filter = ('status', 'bedrooms')