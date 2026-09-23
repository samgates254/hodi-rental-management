from rest_framework import serializers

from .models import Building, Property, Unit


class PropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = ('id', 'organization', 'name', 'address', 'city', 'country', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class BuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Building
        fields = ('id', 'property', 'name', 'created_at')
        read_only_fields = ('id', 'created_at')


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ('id', 'building', 'name', 'status', 'bedrooms', 'metadata', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')
