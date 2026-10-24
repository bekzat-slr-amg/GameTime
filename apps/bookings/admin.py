from django.contrib import admin

from .models import Booking, ClubSettings


@admin.register(ClubSettings)
class ClubSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "opening_time", "closing_time", "timezone")

    def changelist_view(self, request, extra_context=None):
        ClubSettings.load()  # гарантируем, что единственная запись существует
        return super().changelist_view(request, extra_context)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "equipment", "user", "start_at", "end_at", "status", "total_price")
    list_filter = ("status", "equipment__zone", "equipment__type")
    search_fields = ("user__email", "equipment__name")
    date_hierarchy = "start_at"
    list_select_related = ("equipment", "user")
    # Брони создаются только через сервис (там проверки). В админке меняем статус.
    readonly_fields = ("user", "equipment", "start_at", "end_at", "rate_snapshot", "total_price", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False