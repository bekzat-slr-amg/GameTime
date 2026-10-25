from django.utils import timezone
from django.views.generic import TemplateView

from apps.bookings.models import ClubSettings

from . import reports
from .permissions import ClubAdminRequiredMixin


class ReportView(ClubAdminRequiredMixin, TemplateView):
    template_name = "club/reports.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        club = ClubSettings.load()
        today = timezone.now().astimezone(club.tzinfo).date()
        start, end, note = reports.parse_range(
            self.request.GET.get("from"), self.request.GET.get("to"), today
        )
        ctx.update({
            "start": start,
            "end": end,
            "note": note,
            "report": reports.build_report(start, end, club.tzinfo),
        })
        return ctx
