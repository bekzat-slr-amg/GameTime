from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.equipment.models import Equipment, Zone

from .models import Booking, ClubSettings
from .services import BookingError, cancel_booking, create_booking

TZ = ZoneInfo("Asia/Bishkek")
NOW = datetime(2026, 10, 24, 9, 0, tzinfo=TZ)


def at(hour, minute=0, day=26):
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


class Base:
    def setUp(self):
        ClubSettings.load()
        self.zone = Zone.objects.create(name="Alpha")
        self.equipment = Equipment.objects.create(zone=self.zone, name="PC 1", type="pc", hourly_rate=Decimal("200"))
        self.user = User.objects.create_user(email="client@example.com", password="x")
        self.other = User.objects.create_user(email="other@example.com", password="x")

    def make(self, user=None, start=None, end=None, status=Booking.Status.CONFIRMED):
        booking = create_booking(
            user=user or self.user, equipment_id=self.equipment.pk,
            start_at=start or at(12), end_at=end or at(13), now=NOW,
        )
        if status != Booking.Status.CONFIRMED:
            booking.status = status
            booking.save()
        return booking

    def make_raw(self, start, end, status=Booking.Status.CONFIRMED, user=None):
        """Бронь напрямую в БД: для прошлого времени, где сервис её не создаст."""
        return Booking.objects.create(
            user=user or self.user, equipment=self.equipment, start_at=start, end_at=end,
            status=status, rate_snapshot=Decimal("200"), total_price=Decimal("200"),
        )


class CancelServiceTests(Base, TestCase):
    def test_owner_can_cancel_future_booking_and_slot_is_freed(self):
        booking = self.make()
        cancel_booking(booking_id=booking.pk, user=self.user, now=NOW)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.make(user=self.other)  # тот же интервал снова доступен

    def test_other_user_cannot_cancel(self):
        booking = self.make()
        with self.assertRaises(BookingError):
            cancel_booking(booking_id=booking.pk, user=self.other, now=NOW)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_started_booking_cannot_be_cancelled(self):
        booking = self.make()
        with self.assertRaises(BookingError):
            cancel_booking(booking_id=booking.pk, user=self.user, now=at(12, 30))

    def test_non_confirmed_statuses_cannot_be_cancelled(self):
        for status in (Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED,
                       Booking.Status.CANCELLED, Booking.Status.NO_SHOW):
            with self.subTest(status=status):
                booking = Booking.objects.create(
                    user=self.user, equipment=self.equipment, status=status,
                    start_at=at(15), end_at=at(16), rate_snapshot=Decimal("200"), total_price=Decimal("200"),
                ) if status not in (Booking.Status.IN_PROGRESS,) else self.make_raw(at(17), at(18), status)
                with self.assertRaises(BookingError):
                    cancel_booking(booking_id=booking.pk, user=self.user, now=NOW)
                booking.refresh_from_db()
                self.assertEqual(booking.status, status)

    def test_unknown_booking_is_rejected(self):
        with self.assertRaises(BookingError):
            cancel_booking(booking_id=99999, user=self.user, now=NOW)


class MyBookingsViewTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("bookings:mine")
        self.client.force_login(self.user)
        now = timezone.now()
        self.future = self.make_raw(now + timedelta(days=2), now + timedelta(days=2, hours=1))
        self.running = self.make_raw(now - timedelta(minutes=30), now + timedelta(minutes=30))
        self.finished = self.make_raw(now - timedelta(days=2), now - timedelta(days=2) + timedelta(hours=1))
        self.cancelled = self.make_raw(now + timedelta(days=3), now + timedelta(days=3, hours=1),
                                       status=Booking.Status.CANCELLED)
        self.no_show = self.make_raw(now - timedelta(days=3), now - timedelta(days=3) + timedelta(hours=1),
                                     status=Booking.Status.NO_SHOW)
        self.foreign = self.make_raw(now + timedelta(days=4), now + timedelta(days=4, hours=1), user=self.other)

    def ids(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return {b.pk for b in response.context["bookings"]}

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertTrue(response.url.startswith(reverse("accounts:login")))

    def test_default_tab_is_upcoming(self):
        self.assertEqual(self.ids(), {self.future.pk})

    def test_each_tab_shows_only_its_bookings(self):
        self.assertEqual(self.ids(status="current"), {self.running.pk})
        self.assertEqual(self.ids(status="completed"), {self.finished.pk})
        self.assertEqual(self.ids(status="cancelled"), {self.cancelled.pk})
        self.assertEqual(self.ids(status="no_show"), {self.no_show.pk})

    def test_other_users_bookings_are_never_listed(self):
        for tab in ("upcoming", "current", "completed", "cancelled", "no_show"):
            self.assertNotIn(self.foreign.pk, self.ids(status=tab))

    def test_unknown_tab_falls_back_to_upcoming(self):
        self.assertEqual(self.ids(status="xyz"), {self.future.pk})

    def test_empty_tab_shows_message(self):
        Booking.objects.filter(user=self.user, status=Booking.Status.NO_SHOW).delete()
        self.assertContains(self.client.get(self.url, {"status": "no_show"}), "Здесь пока пусто")


class BookingDetailAndCancelViewTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.booking = self.make_raw(now + timedelta(days=2), now + timedelta(days=2, hours=1))
        self.client.force_login(self.user)

    def test_owner_sees_details_and_cancel_button(self):
        response = self.client.get(reverse("bookings:detail", args=[self.booking.pk]))
        self.assertContains(response, "Отменить бронь")

    def test_foreign_booking_detail_is_404(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("bookings:detail", args=[self.booking.pk])).status_code, 404)

    def test_anonymous_detail_redirects_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("bookings:detail", args=[self.booking.pk]))
        self.assertTrue(response.url.startswith(reverse("accounts:login")))

    def test_cancel_requires_post(self):
        self.assertEqual(self.client.get(reverse("bookings:cancel", args=[self.booking.pk])).status_code, 405)

    def test_owner_cancels_via_post(self):
        response = self.client.post(reverse("bookings:cancel", args=[self.booking.pk]))
        self.assertRedirects(response, reverse("bookings:mine"))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)

    def test_foreign_user_cannot_cancel(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("bookings:cancel", args=[self.booking.pk]))
        self.assertRedirects(response, reverse("bookings:mine"))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_anonymous_cannot_cancel(self):
        self.client.logout()
        self.client.post(reverse("bookings:cancel", args=[self.booking.pk]))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_repeated_cancel_is_safe(self):
        url = reverse("bookings:cancel", args=[self.booking.pk])
        self.client.post(url)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)
        self.assertIn("нельзя отменить", [str(m) for m in get_messages(response.wsgi_request)][-1])

    def test_started_booking_has_no_cancel_button_and_cannot_be_cancelled(self):
        now = timezone.now()
        running = self.make_raw(now - timedelta(minutes=10), now + timedelta(minutes=50))
        self.assertNotContains(self.client.get(reverse("bookings:detail", args=[running.pk])), "Отменить бронь")
        self.client.post(reverse("bookings:cancel", args=[running.pk]))
        running.refresh_from_db()
        self.assertEqual(running.status, Booking.Status.CONFIRMED)