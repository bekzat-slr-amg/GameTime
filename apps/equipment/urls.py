from django.urls import path

from apps.bookings.views import SlotsView

from . import views

app_name = "equipment"

urlpatterns = [
    path("", views.EquipmentListView.as_view(), name="list"),
    path("<int:pk>/", views.EquipmentDetailView.as_view(), name="detail"),
    path("<int:pk>/slots/", SlotsView.as_view(), name="slots"),
]