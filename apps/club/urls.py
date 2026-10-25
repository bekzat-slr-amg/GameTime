from django.urls import path

from . import report_views, views

app_name = "club"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("reports/", report_views.ReportView.as_view(), name="reports"),
    path("bookings/<int:pk>/start/", views.BookingActionView.as_view(action="start"), name="start"),
    path("bookings/<int:pk>/finish/", views.BookingActionView.as_view(action="finish"), name="finish"),
    path("bookings/<int:pk>/no-show/", views.BookingActionView.as_view(action="no_show"), name="no_show"),
]
