from django.urls import path

from . import equipment_views, report_views, views

app_name = "club"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("reports/", report_views.ReportView.as_view(), name="reports"),
    path("equipment/", equipment_views.EquipmentListView.as_view(), name="equipment_list"),
    path("equipment/new/", equipment_views.EquipmentCreateView.as_view(), name="equipment_create"),
    path("equipment/<int:pk>/edit/", equipment_views.EquipmentUpdateView.as_view(), name="equipment_edit"),
    path("equipment/<int:pk>/toggle/", equipment_views.EquipmentToggleView.as_view(), name="equipment_toggle"),
    path("bookings/<int:pk>/start/", views.BookingActionView.as_view(action="start"), name="start"),
    path("bookings/<int:pk>/finish/", views.BookingActionView.as_view(action="finish"), name="finish"),
    path("bookings/<int:pk>/no-show/", views.BookingActionView.as_view(action="no_show"), name="no_show"),
]
