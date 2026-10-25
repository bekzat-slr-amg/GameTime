from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.equipment.models import Equipment, Zone

from . import services
from .models import Booking, ClubSettings

S = Booking.Status
LABEL = "Ожидает отметки клуба"


class AwaitingMarkTests(TestCase):
    def setUp(self):
        ClubSettings.load()
        zone = Zone.objects.create(name="Alpha")
        self.pc = Equipment.objects.create(zone=zone, name="PC Await", type="pc", hourly_rate=Decimal("200"))
        self.user = User.objects.create_user(email="c@example.com", password="x")
        self.admin = User.objects.create_user(email="a@example.com", password="x", role=User.Role.CLUB_ADMIN)

    def make(self, start_delta, status=S.CONFIRMED, hours=1):
        start = timezone.now() + start_delta
        return Booking.objects.create(
            user=self.user, equipment=self.pc, start_at=start, end_at=start + timedelta(hours=hours),
            status=status, rate_snapshot=Decimal("200"), total_price=Decimal("200"),
        )

    def test_client_sees_awaiting_label_for_past_confirmed_booking(self):
        self.make(timedelta(hours=-3))
        self.client.force_login(self.user)
        response = self.client.get(reverse("bookings:mine"), {"status": "completed"})
        self.assertContains(response, LABEL)

    def test_really_completed_booking_still_shows_completed(self):
        self.make(timedelta(hours=-3), status=S.COMPLETED)
        self.client.force_login(self.user)
        response = self.client.get(reverse("bookings:mine"), {"status": "completed"})
        self.assertContains(response, "Завершена")
        self.assertNotContains(response, LABEL)

    def test_future_and_running_bookings_are_not_awaiting(self):
        self.make(timedelta(days=1))
        self.make(timedelta(minutes=-10))
        self.client.force_login(self.user)
        for tab in ("upcoming", "current"):
            with self.subTest(tab=tab):
                self.assertNotContains(self.client.get(reverse("bookings:mine"), {"status": tab}), LABEL)

    def test_detail_and_profile_show_awaiting_label(self):
        booking = self.make(timedelta(hours=-3))
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("bookings:detail", args=[booking.pk])), LABEL)
        self.assertContains(self.client.get(reverse("accounts:profile")), LABEL)

    def test_admin_can_start_or_mark_no_show_after_the_end(self):
        booking = self.make(timedelta(hours=-3))
        self.assertEqual(services.allowed_actions(booking, timezone.now()), ["start", "no_show"])

    def test_late_marking_leads_to_completed_with_revenue(self):
        booking = self.make(timedelta(hours=-3))
        services.start_session(booking_id=booking.pk)
        services.finish_session(booking_id=booking.pk)
        booking.refresh_from_db()
        self.assertEqual(booking.status, S.COMPLETED)

    def test_dashboard_shows_awaiting_badge_and_late_button(self):
        booking = self.make(timedelta(hours=-3))
        self.client.force_login(self.admin)
        day = timezone.localtime(booking.start_at).date().isoformat()
        response = self.client.get(reverse("club:dashboard"), {"date": day})
        self.assertContains(response, "Ожидает отметки")
        self.assertContains(response, "Клиент был")
        self.assertContains(response, "Неявка")

    def test_dashboard_button_for_running_booking_is_still_start(self):
        booking = self.make(timedelta(minutes=-10))
        self.client.force_login(self.admin)
        day = timezone.localtime(booking.start_at).date().isoformat()
        response = self.client.get(reverse("club:dashboard"), {"date": day})
        self.assertContains(response, "Начать")
        self.assertNotContains(response, "Клиент был")
