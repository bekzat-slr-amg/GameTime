from django.contrib import messages
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import UpdateView

from apps.bookings.models import Booking, ClubSettings

from .forms_zones import ClubSettingsForm
from .permissions import ClubAdminRequiredMixin


def count_outside(club):
    """Сколько будущих подтверждённых броней не помещается в рабочие часы клуба."""
    tz = club.tzinfo
    rows = Booking.objects.filter(
        status=Booking.Status.CONFIRMED, end_at__gt=timezone.now()
    ).values_list("start_at", "end_at")
    count = 0
    for start, end in rows:
        local_start, local_end = start.astimezone(tz), end.astimezone(tz)
        if (
            local_start.date() != local_end.date()
            or local_start.time() < club.opening_time
            or local_end.time() > club.closing_time
        ):
            count += 1
    return count


class ClubSettingsView(ClubAdminRequiredMixin, UpdateView):
    form_class = ClubSettingsForm
    template_name = "club/settings_form.html"
    success_url = reverse_lazy("club:settings")

    def get_object(self, queryset=None):
        return ClubSettings.load()

    def form_valid(self, form):
        response = super().form_valid(form)
        outside = count_outside(self.object)
        text = "Часы работы сохранены."
        if outside:
            text += f" Броней вне новых часов: {outside}. Они сохранены, проверьте их в панели клуба."
        messages.success(self.request, text)
        return response
