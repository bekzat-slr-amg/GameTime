from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings import services
from apps.bookings.models import Booking, ClubSettings
from apps.bookings.services import BookingError
from apps.equipment.models import Equipment, Zone

TZ = ZoneInfo("Asia/Bishkek")
DAY = "2026-10-30"
NOW = datetime(2026, 10, 24, 9, 0, tzinfo=TZ)


def at(hour, minute=0, day=30):
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


def last_message(response):
    return [str(m) for m in get_messages(response.wsgi_request)][-1]


class Base:
    def setUp(self):
        ClubSettings.load()
        self.zone = Zone.objects.create(name="Alpha")
        self.zone2 = Zone.objects.create(name="Bravo")
        self.pc = Equipment.objects.create(zone=self.zone, name="PC 1", type="pc", hourly_rate=Decimal("200"))
        self.client_user = User.objects.create_user(email="client@example.com", password="x")
        self.admin_user = User.objects.create_user(email="boss@example.com", password="x", role=User.Role.CLUB_ADMIN)

    def make(self, start, end, status=Booking.Status.CONFIRMED, equipment=None, user=None, price="200"):
        return Booking.objects.create(
            user=user or self.client_user, equipment=equipment or self.pc,
            start_at=start, end_at=end, status=status,
            rate_snapshot=Decimal("200"), total_price=Decimal(price),
        )


class AccessTests(Base, TestCase):
    def live_booking(self):
        now = timezone.now()
        return self.make(now - timedelta(minutes=10), now + timedelta(minutes=50))

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("club:dashboard"))
        self.assertTrue(response.url.startswith(reverse("accounts:login")))

    def test_client_gets_403_page(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("club:dashboard"))
        self.assertContains(response, "Доступ запрещён", status_code=403)

    def test_club_admin_opens_dashboard(self):
        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.get(reverse("club:dashboard")).status_code, 200)

    def test_client_cannot_run_admin_actions(self):
        booking = self.live_booking()
        self.client.force_login(self.client_user)
        for name in ("start", "finish", "no_show"):
            with self.subTest(action=name):
                self.assertEqual(self.client.post(reverse(f"club:{name}", args=[booking.pk])).status_code, 403)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_anonymous_cannot_run_admin_actions(self):
        booking = self.live_booking()
        for name in ("start", "finish", "no_show"):
            with self.subTest(action=name):
                response = self.client.post(reverse(f"club:{name}", args=[booking.pk]))
                self.assertTrue(response.url.startswith(reverse("accounts:login")))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_admin_actions_require_post(self):
        booking = self.live_booking()
        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.get(reverse("club:start", args=[booking.pk])).status_code, 405)

    def test_unknown_page_shows_styled_404(self):
        response = self.client.get("/there-is-no-such-page/")
        self.assertContains(response, "Страница не найдена", status_code=404)


class TransitionTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.booking = self.make(at(12), at(13))

    def status(self):
        self.booking.refresh_from_db()
        return self.booking.status

    def test_full_cycle_confirmed_to_completed(self):
        services.start_session(booking_id=self.booking.pk, now=at(12, 5))
        self.assertEqual(self.status(), Booking.Status.IN_PROGRESS)
        services.finish_session(booking_id=self.booking.pk, now=at(12, 50))
        self.assertEqual(self.status(), Booking.Status.COMPLETED)

    def test_start_allowed_15_minutes_early_but_not_earlier(self):
        with self.assertRaises(BookingError):
            services.start_session(booking_id=self.booking.pk, now=at(11, 44))
        services.start_session(booking_id=self.booking.pk, now=at(11, 45))
        self.assertEqual(self.status(), Booking.Status.IN_PROGRESS)

    def test_start_after_end_is_rejected(self):
        with self.assertRaises(BookingError):
            services.start_session(booking_id=self.booking.pk, now=at(13))
        self.assertEqual(self.status(), Booking.Status.CONFIRMED)

    def test_finish_requires_started_session(self):
        with self.assertRaises(BookingError):
            services.finish_session(booking_id=self.booking.pk, now=at(12, 30))
        self.assertEqual(self.status(), Booking.Status.CONFIRMED)

    def test_no_show_only_after_start(self):
        with self.assertRaises(BookingError):
            services.mark_no_show(booking_id=self.booking.pk, now=at(11, 59))
        services.mark_no_show(booking_id=self.booking.pk, now=at(12))
        self.assertEqual(self.status(), Booking.Status.NO_SHOW)

    def test_no_show_is_possible_after_the_end_too(self):
        services.mark_no_show(booking_id=self.booking.pk, now=at(14))
        self.assertEqual(self.status(), Booking.Status.NO_SHOW)

    def test_started_session_cannot_be_marked_no_show(self):
        services.start_session(booking_id=self.booking.pk, now=at(12, 5))
        with self.assertRaises(BookingError):
            services.mark_no_show(booking_id=self.booking.pk, now=at(12, 30))
        self.assertEqual(self.status(), Booking.Status.IN_PROGRESS)

    def test_terminal_statuses_cannot_be_changed(self):
        for status in (Booking.Status.COMPLETED, Booking.Status.CANCELLED, Booking.Status.NO_SHOW):
            booking = self.make(at(15), at(16), status=status)
            for action in (services.start_session, services.finish_session, services.mark_no_show):
                with self.subTest(status=status, action=action.__name__):
                    with self.assertRaises(BookingError):
                        action(booking_id=booking.pk, now=at(15, 30))
            booking.refresh_from_db()
            self.assertEqual(booking.status, status)

    def test_unknown_booking_is_rejected(self):
        with self.assertRaises(BookingError):
            services.start_session(booking_id=99999)

    def test_interval_is_blocked_while_in_progress_and_freed_after_finish(self):
        services.start_session(booking_id=self.booking.pk, now=at(12, 5))
        with self.assertRaises(BookingError):
            services.create_booking(user=self.client_user, equipment_id=self.pc.pk,
                                    start_at=at(12), end_at=at(13), now=NOW)
        services.finish_session(booking_id=self.booking.pk, now=at(12, 50))
        services.create_booking(user=self.client_user, equipment_id=self.pc.pk,
                                start_at=at(12), end_at=at(13), now=NOW)

    def test_interval_is_freed_after_no_show(self):
        services.mark_no_show(booking_id=self.booking.pk, now=at(12, 30))
        services.create_booking(user=self.client_user, equipment_id=self.pc.pk,
                                start_at=at(12), end_at=at(13), now=NOW)


class ActionViewTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.booking = self.make(now - timedelta(minutes=10), now + timedelta(minutes=50))
        self.client.force_login(self.admin_user)

    def post(self, name, pk=None, **data):
        return self.client.post(reverse(f"club:{name}", args=[pk or self.booking.pk]), data)

    def status(self):
        self.booking.refresh_from_db()
        return self.booking.status

    def test_start_then_finish(self):
        response = self.post("start")
        self.assertIn("Сеанс начат", last_message(response))
        self.assertEqual(response.url, reverse("club:dashboard"))
        self.assertEqual(self.status(), Booking.Status.IN_PROGRESS)
        response = self.post("finish")
        self.assertIn("Сеанс завершён", last_message(response))
        self.assertEqual(self.status(), Booking.Status.COMPLETED)

    def test_no_show(self):
        response = self.post("no_show")
        self.assertIn("Неявка отмечена", last_message(response))
        self.assertEqual(self.status(), Booking.Status.NO_SHOW)

    def test_invalid_transition_shows_error_and_keeps_status(self):
        response = self.post("finish")
        self.assertIn("Завершить можно только начатый", last_message(response))
        self.assertEqual(self.status(), Booking.Status.CONFIRMED)

    def test_double_click_does_not_break_state(self):
        self.post("start")
        response = self.post("start")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.status(), Booking.Status.IN_PROGRESS)

    def test_unknown_booking_gives_message(self):
        response = self.post("start", pk=99999)
        self.assertIn("Бронь не найдена", last_message(response))

    def test_local_next_is_used(self):
        response = self.post("start", next="/club/?date=2026-10-30")
        self.assertEqual(response.url, "/club/?date=2026-10-30")

    def test_foreign_next_is_ignored(self):
        for target in ("https://evil.example/", "//evil.example/", "/accounts/profile/"):
            with self.subTest(target=target):
                response = self.post("start", next=target)
                self.assertEqual(response.url, reverse("club:dashboard"))


class DashboardTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)
        self.url = reverse("club:dashboard")

    def get(self, **params):
        params.setdefault("date", DAY)
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return response

    def ids(self, **params):
        return {b.pk for b in self.get(**params).context["bookings"]}

    def test_shows_only_selected_day(self):
        today_booking = self.make(at(12), at(13))
        next_day = self.make(at(12, day=31), at(13, day=31))
        ids = self.ids()
        self.assertIn(today_booking.pk, ids)
        self.assertNotIn(next_day.pk, ids)

    def test_status_filter(self):
        confirmed = self.make(at(12), at(13))
        cancelled = self.make(at(12), at(13), status=Booking.Status.CANCELLED)
        self.assertEqual(self.ids(status="cancelled"), {cancelled.pk})
        self.assertEqual(self.ids(status="confirmed"), {confirmed.pk})

    def test_zone_filter(self):
        other = Equipment.objects.create(zone=self.zone2, name="PC 2", type="pc", hourly_rate=Decimal("200"))
        in_alpha = self.make(at(12), at(13))
        in_bravo = self.make(at(12), at(13), equipment=other)
        self.assertEqual(self.ids(zone=self.zone2.pk), {in_bravo.pk})
        self.assertEqual(self.ids(zone=self.zone.pk), {in_alpha.pk})

    def test_invalid_params_fall_back_safely(self):
        response = self.client.get(self.url, {"date": "garbage", "status": "xyz", "zone": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["day"], timezone.now().astimezone(TZ).date())
        response = self.client.get(self.url, {"date": "9999-12-31", "zone": "99999999999999999999"})
        self.assertEqual(response.status_code, 200)

    def test_stats_count_active_hours_and_completed_revenue(self):
        self.make(at(12), at(14), price="400")
        self.make(at(14), at(15), status=Booking.Status.IN_PROGRESS)
        self.make(at(15), at(16), status=Booking.Status.COMPLETED, price="250")
        self.make(at(12), at(13), status=Booking.Status.CANCELLED)
        self.make(at(16), at(17), status=Booking.Status.NO_SHOW)
        self.make(at(12, day=31), at(13, day=31), status=Booking.Status.COMPLETED)
        stats = self.get().context["stats"]
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["hours"], 4.0)
        self.assertEqual(stats["revenue"], Decimal("250"))

    def test_empty_day_shows_message_and_zero_stats(self):
        response = self.get()
        self.assertContains(response, "Броней не найдено")
        self.assertEqual(response.context["stats"]["count"], 0)

    def test_buttons_depend_on_booking_state(self):
        now = timezone.now()
        local_day = timezone.localtime(now).date().isoformat()
        self.make(now - timedelta(minutes=10), now + timedelta(minutes=50))
        response = self.get(date=local_day)
        self.assertContains(response, "Начать")
        self.assertContains(response, "Неявка")
        self.assertNotContains(response, "Завершить")

    def test_pagination(self):
        for _ in range(30):
            self.make(at(12), at(13), status=Booking.Status.CANCELLED)
        self.assertEqual(len(self.get().context["bookings"]), 25)
        self.assertEqual(len(self.get(page=2).context["bookings"]), 5)
