from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking
from apps.equipment.models import Equipment, Zone

from .models import User


class ProfileRecentBookingsTests(TestCase):
    def setUp(self):
        zone = Zone.objects.create(name="Alpha")
        self.equipment = Equipment.objects.create(zone=zone, name="PC Recent", type="pc", hourly_rate=Decimal("200"))
        self.user = User.objects.create_user(email="me@example.com", password="x")
        self.other = User.objects.create_user(email="other@example.com", password="x")
        self.client.force_login(self.user)
        self.url = reverse("accounts:profile")

    def make(self, user, days):
        start = timezone.now() + timedelta(days=days)
        return Booking.objects.create(
            user=user, equipment=self.equipment, start_at=start, end_at=start + timedelta(hours=1),
            rate_snapshot=Decimal("200"), total_price=Decimal("200"),
        )

    def test_empty_state(self):
        self.assertContains(self.client.get(self.url), "Бронирований пока нет")

    def test_only_four_latest_own_bookings_are_shown(self):
        mine = [self.make(self.user, days) for days in range(1, 6)]
        foreign = self.make(self.other, 10)
        recent = list(self.client.get(self.url).context["recent_bookings"])
        self.assertEqual([b.pk for b in recent], [b.pk for b in reversed(mine[1:])])
        self.assertNotIn(foreign.pk, [b.pk for b in recent])
