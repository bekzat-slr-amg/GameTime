from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
    path("create/", views.CreateBookingView.as_view(), name="create"),
    path("mine/", views.MyBookingsView.as_view(), name="mine"),
    path("<int:pk>/", views.BookingDetailView.as_view(), name="detail"),
    path("<int:pk>/cancel/", views.CancelBookingView.as_view(), name="cancel"),
]