import threading
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase

from apps.accounts.models import User
from apps.equipment.models import Equipment, Zone

from .models import Booking, ClubSettings
from .services import BookingError, create_booking

TZ = ZoneInfo("Asia/Bishkek")
NOW = datetime(2026, 10, 24, 9, 0, tzinfo=TZ)


def at(hour, minute=0, day=26):
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


class BookingTestBase:
    def setUp(self):
        ClubSettings.load()
        self.zone = Zone.objects.create(name="Alpha")
        self.equipment = Equipment.objects.create(
            zone=self.zone, name="PC 1", type="pc", hourly_rate=Decimal("200")
        )
        self.user = User.objects.create_user(email="client@example.com", password="x")

    def book(self, start, end, equipment=None, user=None, now=NOW):
        return create_booking(
            user=user or self.user,
            equipment_id=(equipment or self.equipment).pk,
            start_at=start,
            end_at=end,
            now=now,
        )


class BookingCreateTests(BookingTestBase, TestCase):
    def test_success_creates_confirmed_booking_with_server_price(self):
        booking = self.book(at(12), at(13, 30))
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertEqual(booking.rate_snapshot, Decimal("200.00"))
        self.assertEqual(booking.total_price, Decimal("300.00"))
        self.assertEqual(Booking.objects.count(), 1)

    def test_start_in_past_is_rejected(self):
        with self.assertRaises(BookingError):
            self.book(at(12), at(13), now=at(12, 30))
        self.assertEqual(Booking.objects.count(), 0)

    def test_end_not_after_start_is_rejected(self):
        for end in (at(12), at(11)):
            with self.assertRaises(BookingError):
                self.book(at(12), end)

    def test_shorter_than_30_minutes_is_rejected(self):
        with self.assertRaises(BookingError):
            self.book(at(12), at(12, 15))

    def test_start_not_on_half_hour_is_rejected(self):
        with self.assertRaises(BookingError):
            self.book(at(12, 15), at(13, 15))

    def test_duration_not_multiple_of_30_is_rejected(self):
        with self.assertRaises(BookingError):
            self.book(at(12), at(12, 45))

    def test_before_opening_is_rejected(self):
        with self.assertRaises(BookingError):
            self.book(at(9, 30), at(10, 30))

    def test_after_closing_is_rejected(self):
        with self.assertRaises(BookingError):
            self.book(at(22, 30), at(23, 30))

    def test_crossing_midnight_is_rejected(self):
        with self.assertRaises(BookingError):
            self.book(at(23), at(0, 0, day=27))

    def test_working_day_boundaries_are_allowed(self):
        self.book(at(10), at(10, 30))
        self.book(at(22, 30), at(23))
        self.assertEqual(Booking.objects.count(), 2)

    def test_club_timezone_is_used_for_working_hours(self):
        utc = ZoneInfo("UTC")
        # 05:00 UTC = 11:00 в Бишкеке: рабочее время
        self.book(datetime(2026, 10, 26, 5, 0, tzinfo=utc), datetime(2026, 10, 26, 6, 0, tzinfo=utc))
        # 03:00 UTC = 09:00 в Бишкеке: клуб ещё закрыт
        with self.assertRaises(BookingError):
            self.book(datetime(2026, 10, 26, 3, 0, tzinfo=utc), datetime(2026, 10, 26, 4, 0, tzinfo=utc))

    def test_inactive_equipment_is_rejected(self):
        self.equipment.is_active = False
        self.equipment.save()
        with self.assertRaises(BookingError):
            self.book(at(12), at(13))

    def test_equipment_in_inactive_zone_is_rejected(self):
        self.zone.is_active = False
        self.zone.save()
        with self.assertRaises(BookingError):
            self.book(at(12), at(13))

    def test_unknown_equipment_is_rejected(self):
        with self.assertRaises(BookingError):
            create_booking(user=self.user, equipment_id=99999, start_at=at(12), end_at=at(13), now=NOW)


class OverlapTests(BookingTestBase, TestCase):
    def setUp(self):
        super().setUp()
        self.book(at(12), at(14))

    def test_partial_overlaps_are_rejected(self):
        for start, end in ((at(11), at(12, 30)), (at(13), at(15))):
            with self.assertRaises(BookingError):
                self.book(start, end)

    def test_contained_and_containing_are_rejected(self):
        for start, end in ((at(12, 30), at(13)), (at(11), at(15))):
            with self.assertRaises(BookingError):
                self.book(start, end)

    def test_adjacent_intervals_are_allowed(self):
        self.book(at(11), at(12))
        self.book(at(14), at(15))
        self.assertEqual(Booking.objects.count(), 3)

    def test_other_equipment_is_not_affected(self):
        other = Equipment.objects.create(zone=self.zone, name="PC 2", type="pc", hourly_rate=Decimal("200"))
        self.book(at(12), at(14), equipment=other)
        self.assertEqual(Booking.objects.count(), 2)

    def test_cancelled_booking_frees_the_interval(self):
        Booking.objects.update(status=Booking.Status.CANCELLED)
        self.book(at(12), at(14))
        self.assertEqual(Booking.objects.filter(status=Booking.Status.CONFIRMED).count(), 1)

    def test_no_show_and_completed_free_the_interval(self):
        for status in (Booking.Status.NO_SHOW, Booking.Status.COMPLETED):
            with self.subTest(status=status):
                Booking.objects.filter(status=Booking.Status.CONFIRMED).update(status=status)
                self.book(at(12), at(14))

    def test_in_progress_booking_blocks_the_interval(self):
        Booking.objects.update(status=Booking.Status.IN_PROGRESS)
        with self.assertRaises(BookingError):
            self.book(at(12), at(13))

    def test_database_constraint_blocks_overlap_without_service(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Booking.objects.create(
                user=self.user, equipment=self.equipment, start_at=at(13), end_at=at(15),
                rate_snapshot=Decimal("200"), total_price=Decimal("400"),
            )


class PriceSnapshotTests(BookingTestBase, TestCase):
    def test_rate_change_does_not_change_saved_booking(self):
        booking = self.book(at(12), at(13))
        self.equipment.hourly_rate = Decimal("999")
        self.equipment.save()
        booking.refresh_from_db()
        self.assertEqual(booking.rate_snapshot, Decimal("200.00"))
        self.assertEqual(booking.total_price, Decimal("200.00"))


class ClubSettingsTests(TestCase):
    def test_closing_must_be_after_opening(self):
        club = ClubSettings(opening_time=at(12).time(), closing_time=at(10).time())
        with self.assertRaises(ValidationError):
            club.full_clean()

    def test_unknown_timezone_is_invalid(self):
        with self.assertRaises(ValidationError):
            ClubSettings(timezone="Mars/Olympus").full_clean()

    def test_settings_is_a_single_row(self):
        ClubSettings.load()
        ClubSettings(opening_time=at(11).time(), closing_time=at(22).time()).save()
        self.assertEqual(ClubSettings.objects.count(), 1)


class ConcurrencyTests(BookingTestBase, TransactionTestCase):
    def test_simultaneous_requests_for_same_slot_only_one_wins(self):
        users = [User.objects.create_user(email=f"u{i}@example.com", password="x") for i in range(4)]
        barrier = threading.Barrier(len(users))
        results = []

        def worker(user):
            try:
                barrier.wait()
                self.book(at(15), at(16), user=user)
                results.append("ok")
            except BookingError:
                results.append("busy")
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("busy"), 3)
        self.assertEqual(Booking.objects.filter(equipment=self.equipment).count(), 1)