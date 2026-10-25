from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking, ClubSettings
from apps.equipment.models import Equipment, Zone

from . import reports

TZ = ZoneInfo("Asia/Bishkek")
TODAY = date(2026, 10, 25)
S = Booking.Status


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


class ParseRangeTests(SimpleTestCase):
    def test_defaults_to_month_start_and_today(self):
        self.assertEqual(reports.parse_range(None, None, TODAY), (date(2026, 10, 1), TODAY, ""))

    def test_explicit_range(self):
        result = reports.parse_range("2026-10-05", "2026-10-10", TODAY)
        self.assertEqual(result, (date(2026, 10, 5), date(2026, 10, 10), ""))

    def test_reversed_range_is_swapped_with_note(self):
        start, end, note = reports.parse_range("2026-10-10", "2026-10-05", TODAY)
        self.assertEqual((start, end), (date(2026, 10, 5), date(2026, 10, 10)))
        self.assertTrue(note)

    def test_garbage_falls_back_to_defaults(self):
        for value in ("x", "2026-13-40", "9999-01-01", "1999-01-01", ""):
            with self.subTest(value=value):
                start, end, _ = reports.parse_range(value, value, TODAY)
                self.assertEqual((start, end), (date(2026, 10, 1), TODAY))

    def test_range_is_limited_to_a_year(self):
        start, end, note = reports.parse_range("2020-01-01", "2026-10-25", TODAY)
        self.assertEqual(end, TODAY)
        self.assertEqual((end - start).days, reports.MAX_DAYS - 1)
        self.assertTrue(note)


class BuildReportTests(TestCase):
    def setUp(self):
        zone = Zone.objects.create(name="Alpha")
        self.pc1 = Equipment.objects.create(zone=zone, name="PC 1", type="pc", hourly_rate=Decimal("200"))
        self.pc2 = Equipment.objects.create(zone=zone, name="PC 2", type="pc", hourly_rate=Decimal("200"))
        self.user = User.objects.create_user(email="c@example.com", password="x")

    def make(self, start, end, equipment=None, status=S.CONFIRMED, price="200"):
        return Booking.objects.create(
            user=self.user, equipment=equipment or self.pc1, start_at=start, end_at=end,
            status=status, rate_snapshot=Decimal("200"), total_price=Decimal(price),
        )

    def test_totals_and_breakdowns(self):
        self.make(at(26, 12), at(26, 14), status=S.COMPLETED, price="400")
        self.make(at(26, 15), at(26, 16), equipment=self.pc2)
        self.make(at(27, 1), at(27, 2), status=S.COMPLETED, price="200")  # 01:00 по Бишкеку = 26-е по UTC
        self.make(at(26, 18), at(26, 19), status=S.CANCELLED)
        self.make(at(25, 23, 30), at(26, 0, 30), status=S.COMPLETED, price="100")  # до периода
        self.make(at(28, 10), at(28, 11), status=S.NO_SHOW)  # после периода

        report = reports.build_report(date(2026, 10, 26), date(2026, 10, 27), TZ)

        self.assertEqual(report["count"], 3)
        self.assertEqual(report["hours"], 4.0)
        self.assertEqual(report["revenue"], Decimal("600"))
        statuses = {s["status"]: s["count"] for s in report["statuses"]}
        self.assertEqual(statuses, {"confirmed": 1, "in_progress": 0, "completed": 2, "cancelled": 1, "no_show": 0})
        days = [(r["day"], r["count"], r["hours"], r["revenue"]) for r in report["days"]]
        self.assertEqual(days, [
            (date(2026, 10, 26), 2, 3.0, Decimal("400")),
            (date(2026, 10, 27), 1, 1.0, Decimal("200")),
        ])
        equipment = {r["name"]: (r["count"], r["hours"], r["revenue"]) for r in report["equipment"]}
        self.assertEqual(equipment, {"PC 1": (2, 3.0, Decimal("600")), "PC 2": (1, 1.0, 0)})

    def test_booking_belongs_to_the_day_it_starts(self):
        self.make(at(26, 23, 30), at(27, 0, 30))
        self.assertEqual(reports.build_report(date(2026, 10, 26), date(2026, 10, 26), TZ)["count"], 1)
        self.assertEqual(reports.build_report(date(2026, 10, 27), date(2026, 10, 27), TZ)["count"], 0)

    def test_empty_period(self):
        report = reports.build_report(date(2026, 11, 1), date(2026, 11, 2), TZ)
        self.assertEqual((report["count"], report["hours"], report["revenue"]), (0, 0, 0))
        self.assertEqual((report["days"], report["equipment"]), ([], []))
        self.assertTrue(all(s["count"] == 0 for s in report["statuses"]))


class ReportViewTests(TestCase):
    def setUp(self):
        ClubSettings.load()
        self.client_user = User.objects.create_user(email="client@example.com", password="x")
        self.admin_user = User.objects.create_user(email="boss@example.com", password="x", role=User.Role.CLUB_ADMIN)
        self.url = reverse("club:reports")

    def test_anonymous_is_redirected_to_login(self):
        self.assertTrue(self.client.get(self.url).url.startswith(reverse("accounts:login")))

    def test_client_gets_403(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_admin_sees_current_month_by_default(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        today = timezone.now().astimezone(TZ).date()
        self.assertEqual(response.context["start"], today.replace(day=1))
        self.assertEqual(response.context["end"], today)

    def test_garbage_params_do_not_break_page(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(self.url, {"from": "garbage", "to": "9999-99-99"})
        self.assertEqual(response.status_code, 200)

    def test_reversed_dates_show_note(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(self.url, {"from": "2026-10-10", "to": "2026-10-05"})
        self.assertContains(response, "обратном порядке")

    def test_completed_revenue_is_shown(self):
        zone = Zone.objects.create(name="Alpha")
        pc = Equipment.objects.create(zone=zone, name="PC 1", type="pc", hourly_rate=Decimal("250"))
        Booking.objects.create(
            user=self.client_user, equipment=pc, start_at=at(26, 12), end_at=at(26, 13), status=S.COMPLETED,
            rate_snapshot=Decimal("250"), total_price=Decimal("250"),
        )
        self.client.force_login(self.admin_user)
        response = self.client.get(self.url, {"from": "2026-10-26", "to": "2026-10-26"})
        self.assertContains(response, "250 сом")
        self.assertContains(response, "PC 1")
