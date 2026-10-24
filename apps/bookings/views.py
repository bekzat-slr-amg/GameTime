from django.http import Http404
from django.views.generic import DetailView, ListView
from .models import Booking
from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from apps.equipment.views import visible_equipment

from . import services
from .models import Booking, ClubSettings


@method_decorator(never_cache, name="dispatch")
class SlotsView(View):
    """GET /equipment/<id>/slots/?date=YYYY-MM-DD&duration=60 — часть страницы для HTMX."""

    def get(self, request, pk):
        item = get_object_or_404(visible_equipment(), pk=pk)
        context = services.slots_context(item, request.GET.get("date"), request.GET.get("duration"))
        context["item"] = item
        return render(request, "bookings/_slots.html", context)


class CreateBookingView(LoginRequiredMixin, View):
    """POST /bookings/create/ — создать бронь. Цену и конец считает сервер."""

    http_method_names = ["post"]

    def post(self, request):
        now = timezone.now()
        club = ClubSettings.load()

        try:
            equipment_id = int(request.POST.get("equipment", ""))
        except ValueError:
            equipment_id = 0
        if not 0 < equipment_id < 2**31:
            messages.error(request, "Оборудование не выбрано.")
            return redirect("equipment:list")

        day = services.parse_day(request.POST.get("date"), club, now)
        try:
            duration = int(request.POST.get("duration", ""))
        except ValueError:
            duration = None
        start_raw = request.POST.get("start", "")

        error = None
        start_time = None
        if day is None:
            error = "Выберите корректную дату."
        elif duration not in services.DURATIONS:
            error = "Выберите продолжительность."
        elif not start_raw:
            error = "Выберите время начала."
        else:
            try:
                start_time = time.fromisoformat(start_raw)
            except ValueError:
                error = "Некорректное время начала."

        if error is None:
            start_at = datetime.combine(day, start_time, tzinfo=club.tzinfo)
            end_at = start_at + timedelta(minutes=duration)
            try:
                booking = services.create_booking(
                    user=request.user, equipment_id=equipment_id,
                    start_at=start_at, end_at=end_at, now=now,
                )
            except services.BookingError as exc:
                error = str(exc)
            else:
                messages.success(
                    request,
                    f"Бронь подтверждена: {booking.equipment.name}, {start_at:%d.%m.%Y} "
                    f"{start_at:%H:%M}–{end_at:%H:%M}, {booking.total_price} сом.",
                )

        if error:
            messages.error(request, error)
        return redirect(self.back_url(equipment_id, day, duration))

    @staticmethod
    def back_url(equipment_id, day, duration):
        if not visible_equipment().filter(pk=equipment_id).exists():
            return reverse("equipment:list")
        params = {}
        if day:
            params["date"] = day.isoformat()
        if duration in services.DURATIONS:
            params["duration"] = duration
        url = reverse("equipment:detail", args=[equipment_id])
        return f"{url}?{urlencode(params)}" if params else url

TABS = [
    ("upcoming", "Будущие"),
    ("current", "Текущие"),
    ("completed", "Завершённые"),
    ("cancelled", "Отменённые"),
    ("no_show", "Неявки"),
]


def filter_by_tab(qs, tab, now):
    if tab == "current":
        return qs.filter(
            Q(status=Booking.Status.IN_PROGRESS)
            | Q(status=Booking.Status.CONFIRMED, start_at__lte=now, end_at__gt=now)
        )
    if tab == "completed":
        return qs.filter(
            Q(status=Booking.Status.COMPLETED)
            | Q(status=Booking.Status.CONFIRMED, end_at__lte=now)
        )
    if tab == "cancelled":
        return qs.filter(status=Booking.Status.CANCELLED)
    if tab == "no_show":
        return qs.filter(status=Booking.Status.NO_SHOW)
    return qs.filter(status=Booking.Status.CONFIRMED, start_at__gt=now)


class MyBookingsView(LoginRequiredMixin, ListView):
    template_name = "bookings/my_bookings.html"
    context_object_name = "bookings"
    paginate_by = 10

    def current_tab(self):
        tab = self.request.GET.get("status", "upcoming")
        return tab if tab in dict(TABS) else "upcoming"

    def get_queryset(self):
        qs = Booking.objects.filter(user=self.request.user).select_related("equipment", "equipment__zone")
        return filter_by_tab(qs, self.current_tab(), timezone.now())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({"tabs": TABS, "current_tab": self.current_tab(), "now": timezone.now()})
        return ctx


class BookingDetailView(LoginRequiredMixin, DetailView):
    template_name = "bookings/detail.html"
    context_object_name = "booking"

    def get_queryset(self):
        # Только свои брони: чужая по прямому URL не найдётся.
        return Booking.objects.filter(user=self.request.user).select_related("equipment", "equipment__zone")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        booking = self.object
        ctx["now"] = timezone.now()
        ctx["can_cancel"] = booking.status == Booking.Status.CONFIRMED and booking.start_at > timezone.now()
        return ctx


class CancelBookingView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        try:
            booking = services.cancel_booking(booking_id=pk, user=request.user)
        except services.BookingError as exc:
            messages.error(request, str(exc))
            if not Booking.objects.filter(pk=pk, user=request.user).exists():
                return redirect("bookings:mine")
            return redirect("bookings:detail", pk=pk)
        messages.success(request, f"Бронь отменена: {booking.equipment.name}, {timezone.localtime(booking.start_at):%d.%m.%Y %H:%M}.")
        return redirect("bookings:mine")