from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.accounts.models import User

from .models import Booking

PASSWORD = "Demo-pass-2026"
S = Booking.Status


def seed(**kwargs):
    call_command("seed_demo", password=PASSWORD, stdout=StringIO(), **kwargs)


@override_settings(DEBUG=True)
class SeedDemoTests(TestCase):
    def setUp(self):
        call_command("seed_equipment", verbosity=0, stdout=StringIO())

    def demo_bookings(self):
        return Booking.objects.filter(user__email__startswith="demo.client")

    def test_creates_clients_and_bookings_with_different_statuses(self):
        seed()
        self.assertEqual(User.objects.filter(email__startswith="demo.client").count(), 3)
        self.assertTrue(13 <= self.demo_bookings().count() <= 15)
        statuses = set(self.demo_bookings().values_list("status", flat=True))
        for status in (S.COMPLETED, S.CANCELLED, S.NO_SHOW, S.CONFIRMED):
            self.assertIn(status, statuses)

    def test_demo_clients_are_regular_clients_who_can_log_in(self):
        seed()
        user = User.objects.get(email="demo.client1@example.com")
        self.assertEqual(user.role, User.Role.CLIENT)
        self.assertFalse(user.is_staff)
        self.assertTrue(self.client.login(username=user.email, password=PASSWORD))

    def test_prices_follow_rate_snapshot(self):
        seed()
        for booking in self.demo_bookings():
            hours = booking.duration.total_seconds() / 3600
            self.assertEqual(float(booking.total_price), float(booking.rate_snapshot) * hours)

    def test_repeated_run_does_not_duplicate(self):
        seed()
        first = (User.objects.count(), self.demo_bookings().count())
        seed()
        self.assertEqual((User.objects.count(), self.demo_bookings().count()), first)

    def test_other_users_bookings_are_untouched(self):
        other = User.objects.create_user(email="real@example.com", password="x")
        seed()
        mine = Booking.objects.filter(user__email="demo.client1@example.com").first()
        Booking.objects.create(
            user=other, equipment=mine.equipment, start_at=mine.start_at + __import__("datetime").timedelta(days=30),
            end_at=mine.end_at + __import__("datetime").timedelta(days=30),
            rate_snapshot=mine.rate_snapshot, total_price=mine.total_price,
        )
        seed()
        self.assertEqual(Booking.objects.filter(user=other).count(), 1)

    def test_fails_without_equipment(self):
        from apps.equipment.models import Equipment

        Equipment.objects.all().delete()
        with self.assertRaises(CommandError):
            seed()

    def test_refuses_outside_debug_unless_forced(self):
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                seed()
            seed(force=True)
        self.assertEqual(User.objects.filter(email__startswith="demo.client").count(), 3)
