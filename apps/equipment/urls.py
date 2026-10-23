from django.urls import path

from . import views

app_name = "equipment"

urlpatterns = [
    path("", views.EquipmentListView.as_view(), name="list"),
    path("<int:pk>/", views.EquipmentDetailView.as_view(), name="detail"),
]