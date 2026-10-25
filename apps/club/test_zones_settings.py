from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking, ClubSettings
from apps.bookings.services import BookingError, create_booking
from apps.equipment.models import Equipment, Zone

TZ = ZoneInfo("Asia/Bishkek")


def last_message(response):
    return [str(m) for m in get_messages(response.wsgi_request)][-1]


def local_day(days):
    return (timezone.now().astimezone(TZ) + timedelta(days=days)).date()


class Base:
    def setUp(self):
        ClubSettings.load()
        self.alpha = Zone.objects.create(name="Alpha", description="ПК")
        self.bravo = Zone.objects.create(name="Bravo")
        self.pc = Equipment.objects.create(zone=self.alpha, name="Zone Box 1", type="pc", hourly_rate=Decimal("200"))
        self.pc2 = Equipment.objects.create(zone=self.alpha, name="Zone Box 2", type="pc", hourly_rate=Decimal("200"))
        self.client_user = User.objects.create_user(email="client@example.com", password="x")
        self.admin_user = User.objects.create_user(email="boss@example.com", password="x", role=User.Role.CLUB_ADMIN)

    def future_booking(self, equipment=None, days=2, hour=12):
        start = datetime.combine(local_day(days), time(hour, 0), tzinfo=TZ)
        return Booking.objects.create(
            user=self.client_user, equipment=equipment or self.pc, start_at=start,
            end_at=start + timedelta(hours=1), rate_snapshot=Decimal("200"), total_price=Decimal("200"),
        )


class AccessTests(Base, TestCase):
    def urls(self):
        return [
            reverse("club:zone_list"), reverse("club:zone_create"),
            reverse("club:zone_edit", args=[self.alpha.pk]), reverse("club:settings"),
        ]

    def test_anonymous_is_redirected_to_login(self):
        for url in self.urls():
            with self.subTest(url=url):
                self.assertTrue(self.client.get(url).url.startswith(reverse("accounts:login")))

    def test_client_gets_403(self):
        self.client.force_login(self.client_user)
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_admin_opens_pages(self):
        self.client.force_login(self.admin_user)
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_client_cannot_modify_anything(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.post(reverse("club:zone_create"), {"name": "Hack", "is_active": "on"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("club:zone_toggle", args=[self.alpha.pk]), {"active": "0"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("club:settings"), {
            "opening_time": "01:00", "closing_time": "02:00", "timezone": "UTC"}).status_code, 403)
        self.alpha.refresh_from_db()
        self.assertTrue(self.alpha.is_active)
        self.assertFalse(Zone.objects.filter(name="Hack").exists())
        self.assertEqual(ClubSettings.load().opening_time, time(10, 0))

    def test_toggle_requires_post(self):
        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.get(reverse("club:zone_toggle", args=[self.alpha.pk])).status_code, 405)


class ZoneListTests(Base, TestCase):
    def test_inactive_zone_and_counts_are_shown(self):
        self.bravo.is_active = False
        self.bravo.save()
        self.pc2.is_active = False
        self.pc2.save()
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("club:zone_list"))
        counts = {z.name: (z.total, z.active_count) for z in response.context["zones"]}
        self.assertEqual(counts, {"Alpha": (2, 1), "Bravo": (0, 0)})
        self.assertContains(response, "Выключена")


class ZoneFormTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)

    def test_create_success(self):
        response = self.client.post(reverse("club:zone_create"), {"name": "  Charlie ", "description": "VR", "is_active": "on"})
        self.assertRedirects(response, reverse("club:zone_list"))
        self.assertEqual(Zone.objects.get(name="Charlie").description, "VR")
        self.assertIn("добавлена", last_message(response))

    def test_duplicate_or_empty_name_is_rejected(self):
        for name in ("Alpha", "", "   "):
            with self.subTest(name=name):
                response = self.client.post(reverse("club:zone_create"), {"name": name, "is_active": "on"})
                self.assertEqual(response.status_code, 200)
        self.assertEqual(Zone.objects.count(), 2)

    def test_edit_updates_fields_and_keeps_same_name(self):
        url = reverse("club:zone_edit", args=[self.alpha.pk])
        self.assertEqual(self.client.post(url, {"name": "Alpha", "description": "Новое", "is_active": "on"}).status_code, 302)
        self.alpha.refresh_from_db()
        self.assertEqual(self.alpha.description, "Новое")

    def test_rename_to_existing_name_is_rejected(self):
        url = reverse("club:zone_edit", args=[self.alpha.pk])
        self.assertEqual(self.client.post(url, {"name": "Bravo", "is_active": "on"}).status_code, 200)
        self.alpha.refresh_from_db()
        self.assertEqual(self.alpha.name, "Alpha")

    def test_unknown_zone_gives_404(self):
        self.assertEqual(self.client.get(reverse("club:zone_edit", args=[99999])).status_code, 404)


class ZoneToggleTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)
        self.url = reverse("club:zone_toggle", args=[self.alpha.pk])

    def post(self, active, **extra):
        return self.client.post(self.url, {"active": active, **extra})

    def test_disable_hides_zone_equipment_from_catalog(self):
        response = self.post("0")
        self.assertIn("выключена", last_message(response))
        self.alpha.refresh_from_db()
        self.assertFalse(self.alpha.is_active)
        self.assertEqual(list(self.client.get(reverse("equipment:list")).context["items"]), [])
        self.assertEqual(Equipment.objects.filter(zone=self.alpha).count(), 2)

    def test_disable_keeps_and_counts_upcoming_bookings_only_of_this_zone(self):
        first = self.future_booking(self.pc, hour=12)
        self.future_booking(self.pc2, hour=14)
        other = Equipment.objects.create(zone=self.bravo, name="Bravo Box", type="pc", hourly_rate=Decimal("150"))
        self.future_booking(other, hour=16)
        response = self.post("0")
        self.assertIn("сохранены: 2", last_message(response))
        first.refresh_from_db()
        self.assertEqual(first.status, Booking.Status.CONFIRMED)

    def test_disabled_zone_blocks_new_bookings(self):
        self.post("0")
        start = datetime.combine(local_day(1), time(12, 0), tzinfo=TZ)
        with self.assertRaises(BookingError):
            create_booking(user=self.client_user, equipment_id=self.pc.pk, start_at=start, end_at=start + timedelta(hours=1))

    def test_enable_returns_equipment_to_catalog(self):
        self.alpha.is_active = False
        self.alpha.save()
        response = self.post("1")
        self.assertIn("снова включена", last_message(response))
        ids = {i.pk for i in self.client.get(reverse("equipment:list")).context["items"]}
        self.assertEqual(ids, {self.pc.pk, self.pc2.pk})

    def test_repeated_and_invalid_requests_are_safe(self):
        self.post("0")
        self.assertEqual(self.post("0").status_code, 302)
        self.alpha.refresh_from_db()
        self.assertFalse(self.alpha.is_active)
        for value in ("x", "", "2"):
            with self.subTest(value=value):
                self.alpha.is_active = True
                self.alpha.save()
                self.assertIn("Некорректный", last_message(self.post(value)))
                self.alpha.refresh_from_db()
                self.assertTrue(self.alpha.is_active)

    def test_unknown_zone_gives_404(self):
        self.assertEqual(self.client.post(reverse("club:zone_toggle", args=[99999]), {"active": "0"}).status_code, 404)

    def test_next_redirect_is_validated(self):
        self.assertEqual(self.post("0", next="/club/zones/").url, "/club/zones/")
        for target in ("https://evil.example/", "//evil.example/", "/accounts/profile/"):
            with self.subTest(target=target):
                self.assertEqual(self.post("1", next=target).url, reverse("club:zone_list"))


class ClubSettingsTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)
        self.url = reverse("club:settings")

    def post(self, **extra):
        data = {"opening_time": "11:00", "closing_time": "22:00", "timezone": "Asia/Bishkek"}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_save_updates_the_single_row(self):
        response = self.post()
        self.assertRedirects(response, self.url)
        self.assertEqual(ClubSettings.objects.count(), 1)
        club = ClubSettings.load()
        self.assertEqual((club.opening_time, club.closing_time), (time(11, 0), time(22, 0)))
        self.assertIn("Часы работы сохранены", last_message(response))
        self.assertNotIn("вне новых часов", last_message(response))

    def test_invalid_values_change_nothing(self):
        cases = [
            {"closing_time": "10:00"},
            {"closing_time": "09:00"},
            {"timezone": "Mars/Olympus"},
            {"timezone": ""},
            {"opening_time": "abc"},
            {"closing_time": ""},
        ]
        for extra in cases:
            with self.subTest(extra=extra):
                self.assertEqual(self.post(**extra).status_code, 200)
                club = ClubSettings.load()
                self.assertEqual((club.opening_time, club.closing_time, club.timezone),
                                 (time(10, 0), time(23, 0), "Asia/Bishkek"))

    def test_new_hours_apply_to_booking_rules(self):
        self.post()
        day = local_day(1)
        too_early = datetime.combine(day, time(10, 0), tzinfo=TZ)
        with self.assertRaises(BookingError):
            create_booking(user=self.client_user, equipment_id=self.pc.pk,
                           start_at=too_early, end_at=too_early + timedelta(hours=1))
        ok = datetime.combine(day, time(11, 0), tzinfo=TZ)
        create_booking(user=self.client_user, equipment_id=self.pc.pk, start_at=ok, end_at=ok + timedelta(hours=1))

    def test_warns_about_upcoming_bookings_outside_new_hours(self):
        self.future_booking(self.pc, hour=10)
        self.future_booking(self.pc2, hour=15)
        response = self.post(opening_time="12:00")
        self.assertIn("вне новых часов: 1", last_message(response))
        self.assertEqual(Booking.objects.filter(status=Booking.Status.CONFIRMED).count(), 2)

    def test_home_page_shows_hours_from_settings(self):
        self.post(opening_time="09:00", closing_time="20:00")
        self.assertContains(self.client.get(reverse("core:home")), "09:00 – 20:00")
