from django.contrib import admin

from .models import Equipment, Zone


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "zone", "hourly_rate", "is_active", "is_featured")
    list_filter = ("type", "zone", "is_active", "is_featured")
    search_fields = ("name",)