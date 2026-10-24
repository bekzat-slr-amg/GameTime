from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.equipment.models import Equipment, Zone

from .models import Booking, ClubSettings
from .services import BookingError, create_booking, day_slots, parse_day

TZ = ZoneInfo("Asia/Bishkek")
NOW = datetime(2026, 10, 24, 9, 0, tzinfo=TZ)


def at(hour, minute=0, day=26):
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


def tomorrow():
    return (timezone.now().astimezone(TZ) + timedelta(days=1)).date()


def state_of(slots, label):
    return next(slot["state"] for slot in slots if slot["label"] == label)


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


class Base:
    def setUp(self):
        ClubSettings.load()
        self.zone = Zone.objects.create(name="Alpha")
        self.equipment = Equipment.objects.create(
            zone=self.zone, name="PC 1", type="pc", hourly_rate=Decimal("200")
        )
        self.user = User.objects.create_user(email="client@example.com", password="x")
        self.other = User.objects.create_user(email="other@example.com", password="x")


class DaySlotsTests(Base, TestCase):
    def test_slot_grid_covers_working_day(self):
        slots = day_slots(self.equipment, date(2026, 10, 26), 60, now=NOW)
        self.assertEqual(len(slots), 26)
        self.assertEqual(slots[0]["label"], "10:00")
        self.assertEqual(slots[-1]["label"], "22:30")

    def test_past_slots_today(self):
        now = datetime(2026, 10, 24, 12, 15, tzinfo=TZ)
        slots = day_slots(self.equipment, date(2026, 10, 24), 60, now=now)
        self.assertEqual(state_of(slots, "10:00"), "past")
        self.assertEqual(state_of(slots, "12:00"), "past")
        self.assertEqual(state_of(slots, "12:30"), "free")

    def test_slot_that_does_not_fit_before_closing(self):
        slots = day_slots(self.equipment, date(2026, 10, 26), 90, now=NOW)
        self.assertEqual(state_of(slots, "21:30"), "free")
        self.assertEqual(state_of(slots, "22:00"), "outside")

    def test_busy_slots_depend_on_duration_and_adjacent_is_free(self):
        create_booking(user=self.user, equipment_id=self.equipment.pk,
                       start_at=at(12), end_at=at(13, 30), now=NOW)
        slots = day_slots(self.equipment, date(2026, 10, 26), 60, now=NOW)
        self.assertEqual(state_of(slots, "11:00"), "free")
        self.assertEqual(state_of(slots, "11:30"), "busy")
        self.assertEqual(state_of(slots, "13:00"), "busy")
        self.assertEqual(state_of(slots, "13:30"), "free")

    def test_cancelled_booking_frees_slots(self):
        create_booking(user=self.user, equipment_id=self.equipment.pk,
                       start_at=at(12), end_at=at(13), now=NOW)
        Booking.objects.update(status=Booking.Status.CANCELLED)
        slots = day_slots(self.equipment, date(2026, 10, 26), 60, now=NOW)
        self.assertEqual(state_of(slots, "12:00"), "free")

    def test_other_equipment_bookings_do_not_block(self):
        other = Equipment.objects.create(zone=self.zone, name="PC 2", type="pc", hourly_rate=Decimal("200"))
        create_booking(user=self.user, equipment_id=other.pk, start_at=at(12), end_at=at(13), now=NOW)
        slots = day_slots(self.equipment, date(2026, 10, 26), 60, now=NOW)
        self.assertEqual(state_of(slots, "12:00"), "free")


class ParseDayTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.club = ClubSettings.load()

    def test_valid_range(self):
        self.assertEqual(parse_day("2026-10-24", self.club, NOW), date(2026, 10, 24))
        self.assertEqual(parse_day("2026-11-23", self.club, NOW), date(2026, 11, 23))

    def test_invalid_values(self):
        for value in ("2026-10-23", "2026-11-24", "garbage", "", None, "2026-13-40"):
            with self.subTest(value=value):
                self.assertIsNone(parse_day(value, self.club, NOW))

    def test_service_rejects_booking_too_far_ahead(self):
        with self.assertRaises(BookingError):
            create_booking(user=self.user, equipment_id=self.equipment.pk,
                           start_at=datetime(2026, 12, 1, 12, tzinfo=TZ),
                           end_at=datetime(2026, 12, 1, 13, tzinfo=TZ), now=NOW)
        create_booking(user=self.user, equipment_id=self.equipment.pk,
                       start_at=datetime(2026, 11, 23, 12, tzinfo=TZ),
                       end_at=datetime(2026, 11, 23, 13, tzinfo=TZ), now=NOW)


class SlotsViewTests(Base, TestCase):
    def url(self, pk=None):
        return reverse("equipment:slots", args=[pk or self.equipment.pk])

    def test_slots_are_public_and_not_cached(self):
        response = self.client.get(self.url(), {"date": tomorrow().isoformat(), "duration": "60"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(len(response.context["slots"]), 26)

    def test_booked_slot_is_marked_busy(self):
        create_booking(user=self.user, equipment_id=self.equipment.pk,
                       start_at=datetime.combine(tomorrow(), datetime.min.time().replace(hour=12), tzinfo=TZ),
                       end_at=datetime.combine(tomorrow(), datetime.min.time().replace(hour=13), tzinfo=TZ))
        response = self.client.get(self.url(), {"date": tomorrow().isoformat(), "duration": "60"})
        self.assertEqual(state_of(response.context["slots"], "12:00"), "busy")
        self.assertContains(response, "Занято")

    def test_invalid_date_shows_message(self):
        response = self.client.get(self.url(), {"date": "garbage"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["day_valid"])
        self.assertContains(response, "Выберите дату")

    def test_unknown_duration_falls_back_to_default(self):
        response = self.client.get(self.url(), {"date": tomorrow().isoformat(), "duration": "9999"})
        self.assertEqual(response.context["duration"], 60)

    def test_inactive_equipment_returns_404(self):
        self.equipment.is_active = False
        self.equipment.save()
        self.assertEqual(self.client.get(self.url()).status_code, 404)


class CreateBookingViewTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("bookings:create")
        self.client.force_login(self.user)

    def post(self, **extra):
        data = {
            "equipment": self.equipment.pk,
            "date": tomorrow().isoformat(),
            "start": "12:00",
            "duration": "60",
        }
        data.update(extra)
        return self.client.post(self.url, data)

    def test_anonymous_is_redirected_to_login(self):
        self.client.logout()
        response = self.post()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("accounts:login")))
        self.assertEqual(Booking.objects.count(), 0)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_success_creates_booking_for_current_user(self):
        response = self.post()
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("equipment:detail", args=[self.equipment.pk]), response.url)
        booking = Booking.objects.get()
        self.assertEqual(booking.user, self.user)
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertEqual(booking.total_price, Decimal("200.00"))
        self.assertIn("Бронь подтверждена", messages_of(response)[-1])

    def test_price_and_user_from_browser_are_ignored(self):
        self.post(total_price="1", rate_snapshot="1", user=self.other.pk, status="completed")
        booking = Booking.objects.get()
        self.assertEqual(booking.total_price, Decimal("200.00"))
        self.assertEqual(booking.user, self.user)
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_busy_interval_is_rejected_with_message(self):
        day = tomorrow()
        create_booking(user=self.other, equipment_id=self.equipment.pk,
                       start_at=datetime(day.year, day.month, day.day, 12, tzinfo=TZ),
                       end_at=datetime(day.year, day.month, day.day, 13, tzinfo=TZ))
        response = self.post(start="12:30")
        self.assertEqual(Booking.objects.count(), 1)
        self.assertIn("занято", messages_of(response)[-1])

    def test_double_submit_of_same_form_creates_one_booking(self):
        self.post()
        response = self.post()
        self.assertEqual(Booking.objects.count(), 1)
        self.assertIn("занято", messages_of(response)[-1])

    def test_invalid_input_creates_nothing(self):
        cases = [
            {"date": "garbage"},
            {"date": (timezone.now().astimezone(TZ) - timedelta(days=1)).date().isoformat()},
            {"date": (timezone.now().astimezone(TZ) + timedelta(days=40)).date().isoformat()},
            {"duration": "45"},
            {"duration": "99999999999999999999"},
            {"duration": ""},
            {"start": ""},
            {"start": "abc"},
            {"start": "09:00"},
            {"start": "22:30", "duration": "120"},
            {"start": "12:15"},
        ]
        for extra in cases:
            with self.subTest(extra=extra):
                self.post(**extra)
                self.assertEqual(Booking.objects.count(), 0)

    def test_bad_equipment_id_creates_nothing_and_goes_to_catalog(self):
        for value in ("abc", "", "0", "99999999999999999999", "99999"):
            with self.subTest(value=value):
                response = self.post(equipment=value)
                self.assertEqual(response.url, reverse("equipment:list"))
                self.assertEqual(Booking.objects.count(), 0)

    def test_inactive_equipment_cannot_be_booked(self):
        self.equipment.is_active = False
        self.equipment.save()
        response = self.post()
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(response.url, reverse("equipment:list"))


class DetailBookingBlockTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("equipment:detail", args=[self.equipment.pk])

    def test_anonymous_sees_login_link_instead_of_button(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Войдите, чтобы забронировать")
        self.assertNotContains(response, 'id="booking-submit"')

    def test_logged_in_user_sees_booking_button(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.url), 'id="booking-submit"')

    def test_garbage_query_params_do_not_break_page(self):
        response = self.client.get(self.url, {"date": "garbage", "duration": "xyz"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["day_valid"])