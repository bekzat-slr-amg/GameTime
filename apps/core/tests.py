from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.equipment.models import Equipment, Zone


class HomePageTests(TestCase):
    def setUp(self):
        self.zone = Zone.objects.create(name="Alpha", description="ПК")

    def make(self, name, **kwargs):
        data = {"zone": self.zone, "name": name, "type": "pc", "hourly_rate": Decimal("200")}
        data.update(kwargs)
        return Equipment.objects.create(**data)

    def get(self):
        return self.client.get(reverse("core:home"))

    def test_home_opens_with_empty_database(self):
        Zone.objects.all().delete()
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Оборудование скоро появится")

    def test_featured_equipment_is_shown(self):
        self.make("PC Featured", is_featured=True)
        self.assertContains(self.get(), "PC Featured")

    def test_not_featured_equipment_is_hidden_from_popular(self):
        self.make("PC Plain", is_featured=False)
        self.assertNotContains(self.get(), "PC Plain")

    def test_inactive_equipment_is_hidden(self):
        self.make("PC Off", is_featured=True, is_active=False)
        self.assertNotContains(self.get(), "PC Off")

    def test_equipment_in_inactive_zone_is_hidden(self):
        self.zone.is_active = False
        self.zone.save()
        self.make("PC Hidden Zone", is_featured=True)
        self.assertNotContains(self.get(), "PC Hidden Zone")

    def test_tariff_shows_minimum_rate_per_type(self):
        self.make("PC A", hourly_rate=Decimal("250"))
        self.make("PC B", hourly_rate=Decimal("150"))
        tariffs = self.get().context["tariffs"]
        self.assertEqual(len(tariffs), 1)
        self.assertEqual(tariffs[0]["min_rate"], Decimal("150"))

    def test_zone_counts_only_active_places(self):
        self.make("PC On")
        self.make("PC Off", is_active=False)
        zone = self.get().context["zones"][0]
        self.assertEqual(zone.places, 1)