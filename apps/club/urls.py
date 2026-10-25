from django.urls import path

from . import equipment_views, report_views, settings_views, views, zone_views

app_name = "club"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("reports/", report_views.ReportView.as_view(), name="reports"),
    path("settings/", settings_views.ClubSettingsView.as_view(), name="settings"),
    path("zones/", zone_views.ZoneListView.as_view(), name="zone_list"),
    path("zones/new/", zone_views.ZoneCreateView.as_view(), name="zone_create"),
    path("zones/<int:pk>/edit/", zone_views.ZoneUpdateView.as_view(), name="zone_edit"),
    path("zones/<int:pk>/toggle/", zone_views.ZoneToggleView.as_view(), name="zone_toggle"),
    path("equipment/", equipment_views.EquipmentListView.as_view(), name="equipment_list"),
    path("equipment/new/", equipment_views.EquipmentCreateView.as_view(), name="equipment_create"),
    path("equipment/<int:pk>/edit/", equipment_views.EquipmentUpdateView.as_view(), name="equipment_edit"),
    path("equipment/<int:pk>/toggle/", equipment_views.EquipmentToggleView.as_view(), name="equipment_toggle"),
    path("bookings/<int:pk>/start/", views.BookingActionView.as_view(action="start"), name="start"),
    path("bookings/<int:pk>/finish/", views.BookingActionView.as_view(action="finish"), name="finish"),
    path("bookings/<int:pk>/no-show/", views.BookingActionView.as_view(action="no_show"), name="no_show"),
]
