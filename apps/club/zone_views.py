from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.bookings.models import Booking
from apps.equipment.models import Zone

from .equipment_views import safe_next
from .forms_zones import ZoneForm
from .permissions import ClubAdminRequiredMixin


class ZoneListView(ClubAdminRequiredMixin, ListView):
    template_name = "club/zone_list.html"
    context_object_name = "zones"

    def get_queryset(self):
        return Zone.objects.annotate(
            total=Count("equipment"),
            active_count=Count("equipment", filter=Q(equipment__is_active=True)),
        ).order_by("name")


class ZoneCreateView(ClubAdminRequiredMixin, CreateView):
    model = Zone
    form_class = ZoneForm
    template_name = "club/zone_form.html"
    success_url = reverse_lazy("club:zone_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Новая зона"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Зона «{form.instance.name}» добавлена.")
        return super().form_valid(form)


class ZoneUpdateView(ClubAdminRequiredMixin, UpdateView):
    model = Zone
    form_class = ZoneForm
    template_name = "club/zone_form.html"
    success_url = reverse_lazy("club:zone_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Изменить зону"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Изменения сохранены: зона «{form.instance.name}».")
        return super().form_valid(form)


class ZoneToggleView(ClubAdminRequiredMixin, View):
    """POST: active=1 включает зону, active=0 выключает. Повторная отправка безопасна."""

    http_method_names = ["post"]

    def post(self, request, pk):
        zone = get_object_or_404(Zone, pk=pk)
        back = safe_next(request, reverse("club:zone_list"))
        value = request.POST.get("active")
        if value not in ("0", "1"):
            messages.error(request, "Некорректный запрос.")
            return redirect(back)

        make_active = value == "1"
        if zone.is_active != make_active:
            zone.is_active = make_active
            zone.save(update_fields=["is_active"])

        if make_active:
            messages.success(request, f"Зона «{zone.name}» снова включена.")
        else:
            items = zone.equipment.filter(is_active=True).count()
            upcoming = Booking.objects.filter(
                equipment__zone=zone, status=Booking.Status.CONFIRMED, end_at__gt=timezone.now()
            ).count()
            text = (
                f"Зона «{zone.name}» выключена: её оборудование ({items}) скрыто из каталога, "
                "новые брони невозможны."
            )
            if upcoming:
                text += f" Уже созданные брони сохранены: {upcoming}. Проверьте их в панели клуба."
            messages.success(request, text)
        return redirect(back)
