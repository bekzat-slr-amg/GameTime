from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking, ClubSettings
from apps.equipment.models import Equipment, Zone


def last_message(response):
    return [str(m) for m in get_messages(response.wsgi_request)][-1]


class Base:
    def setUp(self):
        ClubSettings.load()
        self.alpha = Zone.objects.create(name="Alpha")
        self.bravo = Zone.objects.create(name="Bravo")
        self.pc = Equipment.objects.create(
            zone=self.alpha, name="Toggle Box 1", type="pc", hourly_rate=Decimal("200"), specs="RTX 4060"
        )
        self.client_user = User.objects.create_user(email="client@example.com", password="x")
        self.admin_user = User.objects.create_user(email="boss@example.com", password="x", role=User.Role.CLUB_ADMIN)

    def form_data(self, **extra):
        data = {
            "zone": self.alpha.pk, "name": "PC New", "type": "pc", "specs": "RTX 4070\ni7",
            "hourly_rate": "250", "image": "", "is_active": "on",
        }
        data.update(extra)
        return data


class AccessTests(Base, TestCase):
    def get_urls(self):
        return [
            reverse("club:equipment_list"),
            reverse("club:equipment_create"),
            reverse("club:equipment_edit", args=[self.pc.pk]),
        ]

    def test_anonymous_is_redirected_to_login(self):
        for url in self.get_urls():
            with self.subTest(url=url):
                self.assertTrue(self.client.get(url).url.startswith(reverse("accounts:login")))

    def test_client_gets_403_on_all_pages(self):
        self.client.force_login(self.client_user)
        for url in self.get_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_client_cannot_create_or_toggle(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.post(reverse("club:equipment_create"), self.form_data()).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("club:equipment_toggle", args=[self.pc.pk]), {"active": "0"}).status_code, 403
        )
        self.pc.refresh_from_db()
        self.assertTrue(self.pc.is_active)
        self.assertFalse(Equipment.objects.filter(name="PC New").exists())

    def test_anonymous_cannot_toggle(self):
        response = self.client.post(reverse("club:equipment_toggle", args=[self.pc.pk]), {"active": "0"})
        self.assertTrue(response.url.startswith(reverse("accounts:login")))
        self.pc.refresh_from_db()
        self.assertTrue(self.pc.is_active)

    def test_admin_opens_pages(self):
        self.client.force_login(self.admin_user)
        for url in self.get_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_toggle_requires_post(self):
        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.get(reverse("club:equipment_toggle", args=[self.pc.pk])).status_code, 405)


class ListTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)
        self.console = Equipment.objects.create(
            zone=self.bravo, name="Console X", type="console", hourly_rate=Decimal("180"), is_active=False
        )
        self.url = reverse("club:equipment_list")

    def ids(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return {item.pk for item in response.context["items"]}

    def test_inactive_equipment_is_listed_for_admin(self):
        self.assertEqual(self.ids(), {self.pc.pk, self.console.pk})

    def test_filters(self):
        self.assertEqual(self.ids(q="console"), {self.console.pk})
        self.assertEqual(self.ids(zone=self.bravo.pk), {self.console.pk})
        self.assertEqual(self.ids(status="inactive"), {self.console.pk})
        self.assertEqual(self.ids(status="active"), {self.pc.pk})

    def test_garbage_filters_are_ignored(self):
        self.assertEqual(self.ids(zone="abc", status="zzz"), {self.pc.pk, self.console.pk})
        self.assertEqual(self.client.get(self.url, {"zone": "9" * 30}).status_code, 200)

    def test_empty_result_shows_message(self):
        self.assertContains(self.client.get(self.url, {"q": "nothing-like-this"}), "Ничего не найдено")

    def test_pagination(self):
        for i in range(23):
            Equipment.objects.create(zone=self.alpha, name=f"Bulk {i:02d}", type="pc", hourly_rate=Decimal("100"))
        self.assertEqual(len(self.ids()), 20)
        self.assertEqual(len(self.ids(page=2)), 5)
        self.assertEqual(self.client.get(self.url, {"page": 3}).status_code, 404)


class CreateTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)
        self.url = reverse("club:equipment_create")

    def post(self, **extra):
        return self.client.post(self.url, self.form_data(**extra))

    def created(self):
        return Equipment.objects.filter(name="PC New").exists()

    def test_success(self):
        response = self.post()
        self.assertRedirects(response, reverse("club:equipment_list"))
        item = Equipment.objects.get(name="PC New")
        self.assertEqual(item.hourly_rate, Decimal("250.00"))
        self.assertEqual(item.zone, self.alpha)
        self.assertFalse(item.is_featured)
        self.assertIn("добавлено", last_message(response))

    def test_featured_flag(self):
        self.post(is_featured="on")
        self.assertTrue(Equipment.objects.get(name="PC New").is_featured)

    def test_invalid_rate_is_rejected(self):
        for value in ("0", "-5", "abc", "", "99999999"):
            with self.subTest(rate=value):
                self.assertEqual(self.post(hourly_rate=value).status_code, 200)
                self.assertFalse(self.created())

    def test_duplicate_name_is_rejected(self):
        self.assertEqual(self.post(name="Toggle Box 1").status_code, 200)
        self.assertEqual(Equipment.objects.filter(name="Toggle Box 1").count(), 1)

    def test_empty_name_zone_and_type_are_rejected(self):
        for extra in ({"name": ""}, {"zone": ""}, {"zone": 99999}, {"type": ""}, {"type": "xyz"}):
            with self.subTest(extra=extra):
                before = Equipment.objects.count()
                self.assertEqual(self.post(**extra).status_code, 200)
                self.assertEqual(Equipment.objects.count(), before)

    def test_inactive_zone_is_rejected(self):
        old = Zone.objects.create(name="Old", is_active=False)
        self.post(zone=old.pk)
        self.assertFalse(self.created())

    def test_bad_image_paths_are_rejected(self):
        with mock.patch("apps.club.forms.finders.find", return_value="/abs/file.png"):
            for path in ("../secret.png", "images/../x.png", "http://evil.example/x.png", "images/x.gif",
                         "/etc/passwd", "other/x.png", "images/"):
                with self.subTest(path=path):
                    self.assertEqual(self.post(image=path).status_code, 200)
                    self.assertFalse(self.created())

    def test_missing_image_file_is_rejected(self):
        with mock.patch("apps.club.forms.finders.find", return_value=None):
            response = self.post(image="images/nope.png")
        self.assertContains(response, "Файл не найден")
        self.assertFalse(self.created())

    def test_valid_image_is_saved(self):
        with mock.patch("apps.club.forms.finders.find", return_value="/abs/e-1.png"):
            self.post(image="images/e-1.png")
        self.assertEqual(Equipment.objects.get(name="PC New").image, "images/e-1.png")


class EditTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)
        self.url = reverse("club:equipment_edit", args=[self.pc.pk])

    def post(self, **extra):
        return self.client.post(self.url, self.form_data(**extra))

    def test_update_changes_fields(self):
        response = self.post(name="Renamed Box", hourly_rate="300", zone=self.bravo.pk, type="console")
        self.assertRedirects(response, reverse("club:equipment_list"))
        self.pc.refresh_from_db()
        self.assertEqual((self.pc.name, self.pc.hourly_rate, self.pc.zone, self.pc.type),
                         ("Renamed Box", Decimal("300.00"), self.bravo, "console"))

    def test_keeping_the_same_name_is_allowed(self):
        self.assertEqual(self.post(name="Toggle Box 1").status_code, 302)

    def test_renaming_to_another_existing_name_is_rejected(self):
        Equipment.objects.create(zone=self.alpha, name="Taken", type="pc", hourly_rate=Decimal("100"))
        self.assertEqual(self.post(name="Taken").status_code, 200)
        self.pc.refresh_from_db()
        self.assertEqual(self.pc.name, "Toggle Box 1")

    def test_rate_change_does_not_change_existing_booking(self):
        start = timezone.now() + timedelta(days=1)
        booking = Booking.objects.create(
            user=self.client_user, equipment=self.pc, start_at=start, end_at=start + timedelta(hours=1),
            rate_snapshot=Decimal("200"), total_price=Decimal("200"),
        )
        self.post(name="Toggle Box 1", hourly_rate="999")
        booking.refresh_from_db()
        self.assertEqual((booking.rate_snapshot, booking.total_price), (Decimal("200.00"), Decimal("200.00")))

    def test_equipment_in_inactive_zone_can_still_be_edited(self):
        self.alpha.is_active = False
        self.alpha.save()
        self.assertEqual(self.post(name="Still Editable").status_code, 302)

    def test_inactive_equipment_can_be_edited(self):
        self.pc.is_active = False
        self.pc.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_unknown_equipment_gives_404(self):
        self.assertEqual(self.client.get(reverse("club:equipment_edit", args=[99999])).status_code, 404)


class ToggleTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)
        self.url = reverse("club:equipment_toggle", args=[self.pc.pk])

    def post(self, active, **extra):
        return self.client.post(self.url, {"active": active, **extra})

    def booking(self, delta, status=Booking.Status.CONFIRMED):
        start = timezone.now() + delta
        return Booking.objects.create(
            user=self.client_user, equipment=self.pc, start_at=start, end_at=start + timedelta(hours=1),
            status=status, rate_snapshot=Decimal("200"), total_price=Decimal("200"),
        )

    def test_disable_hides_equipment_from_catalog(self):
        response = self.post("0")
        self.assertIn("выключено", last_message(response))
        self.pc.refresh_from_db()
        self.assertFalse(self.pc.is_active)
        self.assertNotContains(self.client.get(reverse("equipment:list")), "Toggle Box 1")

    def test_enable_returns_equipment_to_catalog(self):
        self.pc.is_active = False
        self.pc.save()
        response = self.post("1")
        self.assertIn("снова доступно", last_message(response))
        self.assertContains(self.client.get(reverse("equipment:list")), "Toggle Box 1")

    def test_disable_reports_upcoming_bookings_and_keeps_them(self):
        upcoming = self.booking(timedelta(days=1))
        self.booking(timedelta(days=2), status=Booking.Status.CANCELLED)
        self.booking(timedelta(days=-2))
        response = self.post("0")
        self.assertIn("сохранены: 1", last_message(response))
        upcoming.refresh_from_db()
        self.assertEqual(upcoming.status, Booking.Status.CONFIRMED)
        self.assertEqual(Booking.objects.filter(equipment=self.pc).count(), 3)

    def test_repeated_requests_are_safe(self):
        self.post("0")
        self.assertEqual(self.post("0").status_code, 302)
        self.pc.refresh_from_db()
        self.assertFalse(self.pc.is_active)

    def test_invalid_value_changes_nothing(self):
        for value in ("x", "", "2", "true"):
            with self.subTest(value=value):
                self.assertIn("Некорректный", last_message(self.post(value)))
                self.pc.refresh_from_db()
                self.assertTrue(self.pc.is_active)

    def test_unknown_equipment_gives_404(self):
        response = self.client.post(reverse("club:equipment_toggle", args=[99999]), {"active": "0"})
        self.assertEqual(response.status_code, 404)

    def test_next_redirect_is_validated(self):
        self.assertEqual(self.post("0", next="/club/equipment/?q=toggle").url, "/club/equipment/?q=toggle")
        for target in ("https://evil.example/", "//evil.example/", "/accounts/profile/"):
            with self.subTest(target=target):
                self.assertEqual(self.post("1", next=target).url, reverse("club:equipment_list"))
