from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import DurationField, ExpressionWrapper, F, Sum
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import ListView

from apps.bookings import services
from apps.bookings.models import Booking, ClubSettings
from apps.equipment.models import Zone

from .permissions import ClubAdminRequiredMixin

ACTIVE_STATUSES = [Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED]


def parse_day(value, today):
    try:
        day = date.fromisoformat(value or "")
    except ValueError:
        return today
    return day if 2000 <= day.year <= 2100 else today


def day_bounds(day, tz):
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start, datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)


class DashboardView(ClubAdminRequiredMixin, ListView):
    template_name = "club/dashboard.html"
    context_object_name = "bookings"
    paginate_by = 25

    @cached_property
    def club(self):
        return ClubSettings.load()

    @cached_property
    def today(self):
        return timezone.now().astimezone(self.club.tzinfo).date()

    @cached_property
    def day(self):
        return parse_day(self.request.GET.get("date"), self.today)

    @cached_property
    def status(self):
        value = self.request.GET.get("status", "")
        return value if value in Booking.Status.values else ""

    @cached_property
    def zone(self):
        value = self.request.GET.get("zone", "")
        return int(value) if value.isascii() and value.isdigit() and len(value) <= 9 else None

    def day_queryset(self):
        start, end = day_bounds(self.day, self.club.tzinfo)
        return Booking.objects.filter(start_at__gte=start, start_at__lt=end)

    def get_queryset(self):
        qs = (
            self.day_queryset()
            .select_related("user", "equipment__zone")
            .order_by("start_at", "equipment__name")
        )
        if self.status:
            qs = qs.filter(status=self.status)
        if self.zone:
            qs = qs.filter(equipment__zone_id=self.zone)
        return qs

    def stats(self):
        day_qs = self.day_queryset()
        active = day_qs.filter(status__in=ACTIVE_STATUSES)
        duration = ExpressionWrapper(F("end_at") - F("start_at"), output_field=DurationField())
        total = active.aggregate(total=Sum(duration))["total"]
        revenue = day_qs.filter(status=Booking.Status.COMPLETED).aggregate(total=Sum("total_price"))["total"]
        return {
            "count": active.count(),
            "hours": round(total.total_seconds() / 3600, 1) if total else 0,
            "revenue": revenue or 0,
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        now = timezone.now()
        rows = list(ctx["page_obj"].object_list)
        for booking in rows:
            booking.actions = services.allowed_actions(booking, now)

        filters = {}
        if self.status:
            filters["status"] = self.status
        if self.zone:
            filters["zone"] = self.zone

        ctx.update({
            "bookings": rows,
            "now": now,
            "day": self.day,
            "today": self.today,
            "prev_day": self.day - timedelta(days=1),
            "next_day": self.day + timedelta(days=1),
            "stats": self.stats(),
            "statuses": Booking.Status.choices,
            "zones": Zone.objects.all(),
            "current_status": self.status,
            "current_zone": str(self.zone or ""),
            "filter_query": urlencode(filters),
            "page_query": urlencode({"date": self.day.isoformat(), **filters}),
        })
        return ctx


HANDLERS = {
    "start": services.start_session,
    "finish": services.finish_session,
    "no_show": services.mark_no_show,
}
SUCCESS = {"start": "Сеанс начат", "finish": "Сеанс завершён", "no_show": "Неявка отмечена"}


class BookingActionView(ClubAdminRequiredMixin, View):
    """POST /club/bookings/<id>/start|finish|no-show/ — смена статуса администратором."""

    http_method_names = ["post"]
    action = None

    def post(self, request, pk):
        try:
            booking = HANDLERS[self.action](booking_id=pk)
        except services.BookingError as exc:
            messages.error(request, str(exc))
        else:
            start = timezone.localtime(booking.start_at)
            end = timezone.localtime(booking.end_at)
            messages.success(
                request,
                f"{SUCCESS[self.action]}: {booking.equipment.name}, {start:%d.%m %H:%M}–{end:%H:%M}.",
            )
        return redirect(self.next_url(request))

    @staticmethod
    def next_url(request):
        target = request.POST.get("next", "")
        if target.startswith("/club/") and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}
        ):
            return target
        return reverse("club:dashboard")