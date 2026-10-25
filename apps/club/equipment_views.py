from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.bookings.models import Booking
from apps.equipment.models import Equipment, Zone

from .forms import EquipmentForm
from .permissions import ClubAdminRequiredMixin


def parse_filters(params):
    """Только допустимые значения фильтров, мусор отбрасывается."""
    filters = {}
    q = params.get("q", "").strip()[:80]
    if q:
        filters["q"] = q
    zone = params.get("zone", "")
    if zone.isascii() and zone.isdigit() and len(zone) <= 9:
        filters["zone"] = zone
    status = params.get("status", "")
    if status in ("active", "inactive"):
        filters["status"] = status
    return filters


def safe_next(request, default):
    target = request.POST.get("next", "")
    if target.startswith("/club/") and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return default


class EquipmentListView(ClubAdminRequiredMixin, ListView):
    template_name = "club/equipment_list.html"
    context_object_name = "items"
    paginate_by = 20

    def get_queryset(self):
        qs = Equipment.objects.select_related("zone")
        filters = parse_filters(self.request.GET)
        if "q" in filters:
            qs = qs.filter(name__icontains=filters["q"])
        if "zone" in filters:
            qs = qs.filter(zone_id=int(filters["zone"]))
        if filters.get("status") == "active":
            qs = qs.filter(is_active=True)
        elif filters.get("status") == "inactive":
            qs = qs.filter(is_active=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        filters = parse_filters(self.request.GET)
        ctx.update({
            "zones": Zone.objects.all(),
            "q": filters.get("q", ""),
            "current_zone": filters.get("zone", ""),
            "current_status": filters.get("status", ""),
            "page_query": urlencode(filters),
            "has_filters": bool(filters),
        })
        return ctx


class EquipmentCreateView(ClubAdminRequiredMixin, CreateView):
    model = Equipment
    form_class = EquipmentForm
    template_name = "club/equipment_form.html"
    success_url = reverse_lazy("club:equipment_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Новое оборудование"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Оборудование «{form.instance.name}» добавлено.")
        return super().form_valid(form)


class EquipmentUpdateView(ClubAdminRequiredMixin, UpdateView):
    model = Equipment
    form_class = EquipmentForm
    template_name = "club/equipment_form.html"
    success_url = reverse_lazy("club:equipment_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Изменить оборудование"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Изменения сохранены: «{form.instance.name}».")
        return super().form_valid(form)


class EquipmentToggleView(ClubAdminRequiredMixin, View):
    """POST: active=1 включает, active=0 выключает. Повторная отправка безопасна."""

    http_method_names = ["post"]

    def post(self, request, pk):
        item = get_object_or_404(Equipment, pk=pk)
        back = safe_next(request, reverse("club:equipment_list"))
        value = request.POST.get("active")
        if value not in ("0", "1"):
            messages.error(request, "Некорректный запрос.")
            return redirect(back)

        make_active = value == "1"
        if item.is_active != make_active:
            item.is_active = make_active
            item.save(update_fields=["is_active"])

        if make_active:
            messages.success(request, f"«{item.name}» снова доступно для брони.")
        else:
            upcoming = Booking.objects.filter(
                equipment=item, status=Booking.Status.CONFIRMED, end_at__gt=timezone.now()
            ).count()
            text = f"«{item.name}» выключено: новые брони невозможны."
            if upcoming:
                text += f" Уже созданные брони сохранены: {upcoming}. Проверьте их в панели клуба."
            messages.success(request, text)
        return redirect(back)
