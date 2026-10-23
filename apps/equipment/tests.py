from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import Equipment, Zone


class CatalogTests(TestCase):
    def setUp(self):
        self.alpha = Zone.objects.create(name="Alpha")
        self.bravo = Zone.objects.create(name="Bravo")
        self.url = reverse("equipment:list")

    def make(self, name, zone=None, **kwargs):
        data = {"zone": zone or self.alpha, "name": name, "type": "pc", "hourly_rate": Decimal("200")}
        data.update(kwargs)
        return Equipment.objects.create(**data)

    def test_list_opens_and_shows_active_equipment(self):
        self.make("Visible Box")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Box")

    def test_search_is_case_insensitive(self):
        self.make("Ryzen Box")
        self.make("Intel Box")
        response = self.client.get(self.url, {"q": "ryzen"})
        self.assertContains(response, "Ryzen Box")
        self.assertNotContains(response, "Intel Box")

    def test_type_filter(self):
        self.make("Gamma PC")
        self.make("Delta Console", type="console")
        response = self.client.get(self.url, {"type": "console"})
        self.assertContains(response, "Delta Console")
        self.assertNotContains(response, "Gamma PC")

    def test_zone_filter(self):
        self.make("Epsilon Box", zone=self.alpha)
        self.make("Zeta Box", zone=self.bravo)
        response = self.client.get(self.url, {"zone": self.bravo.pk})
        self.assertContains(response, "Zeta Box")
        self.assertNotContains(response, "Epsilon Box")

    def test_inactive_equipment_is_hidden(self):
        self.make("Switched Off Box", is_active=False)
        self.assertNotContains(self.client.get(self.url), "Switched Off Box")

    def test_equipment_in_inactive_zone_is_hidden(self):
        self.bravo.is_active = False
        self.bravo.save()
        self.make("Hidden Zone Box", zone=self.bravo)
        self.assertNotContains(self.client.get(self.url), "Hidden Zone Box")

    def test_invalid_filters_are_ignored(self):
        self.make("Still Visible Box")
        response = self.client.get(self.url, {"zone": "abc", "type": "xyz", "q": ""})
        self.assertContains(response, "Still Visible Box")
        response = self.client.get(self.url, {"zone": "99999999999999999999"})
        self.assertEqual(response.status_code, 200)

    def test_pagination(self):
        for i in range(12):
            self.make(f"Item {i:02d}")
        first = self.client.get(self.url)
        self.assertEqual(len(first.context["page_obj"]), 9)
        second = self.client.get(self.url, {"page": 2})
        self.assertEqual(len(second.context["page_obj"]), 3)
        self.assertEqual(self.client.get(self.url, {"page": 3}).status_code, 404)

    def test_empty_state(self):
        response = self.client.get(self.url, {"q": "nothing-like-this"})
        self.assertContains(response, "Ничего не найдено")


class DetailTests(TestCase):
    def setUp(self):
        self.zone = Zone.objects.create(name="Alpha")

    def make(self, **kwargs):
        data = {"zone": self.zone, "name": "Detail Box", "type": "pc", "hourly_rate": Decimal("200"),
                "specs": "RTX 4060\ni5-12400F"}
        data.update(kwargs)
        return Equipment.objects.create(**data)

    def test_detail_opens(self):
        item = self.make()
        response = self.client.get(reverse("equipment:detail", args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail Box")
        self.assertContains(response, "RTX 4060")

    def test_inactive_equipment_returns_404(self):
        item = self.make(is_active=False)
        self.assertEqual(self.client.get(reverse("equipment:detail", args=[item.pk])).status_code, 404)

    def test_unknown_equipment_returns_404(self):
        self.assertEqual(self.client.get(reverse("equipment:detail", args=[99999])).status_code, 404)