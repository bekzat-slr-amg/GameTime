from django.views.generic import DetailView, ListView
from apps.bookings.services import slots_context
from .models import Equipment, Zone


def visible_equipment():
    return Equipment.objects.filter(is_active=True, zone__is_active=True).select_related("zone")


class EquipmentListView(ListView):
    template_name = "equipment/list.html"
    context_object_name = "items"
    paginate_by = 9

    def get_queryset(self):
        qs = visible_equipment()
        params = self.request.GET

        q = params.get("q", "").strip()[:80]
        if q:
            qs = qs.filter(name__icontains=q)

        kind = params.get("type", "")
        if kind in Equipment.Type.values:
            qs = qs.filter(type=kind)

        zone = params.get("zone", "")
        if zone.isascii() and zone.isdigit() and len(zone) <= 9:
            qs = qs.filter(zone_id=int(zone))

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        kind = self.request.GET.get("type", "")
        ctx.update({
            "q": self.request.GET.get("q", "").strip()[:80],
            "current_type": kind if kind in Equipment.Type.values else "",
            "current_zone": self.request.GET.get("zone", ""),
            "types": Equipment.Type.choices,
            "zones": Zone.objects.filter(is_active=True),
            "query": params.urlencode(),
            "has_filters": bool(params),
        })
        return ctx


class EquipmentDetailView(DetailView):
    template_name = "equipment/detail.html"
    context_object_name = "item"

    def get_queryset(self):
        return visible_equipment()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(slots_context(
            self.object, self.request.GET.get("date"), self.request.GET.get("duration")
        ))
        return ctx