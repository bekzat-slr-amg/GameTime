from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from .models import Equipment, Zone


class EquipmentModelTests(TestCase):
    def setUp(self):
        self.zone = Zone.objects.create(name="Alpha")

    def make(self, **kwargs):
        data = {"zone": self.zone, "name": "PC 1", "type": Equipment.Type.PC, "hourly_rate": Decimal("200")}
        data.update(kwargs)
        return Equipment(**data)

    def test_specs_list_skips_empty_lines(self):
        item = self.make(specs="RTX 4060\n\n  i5-12400F  \n")
        self.assertEqual(item.specs_list, ["RTX 4060", "i5-12400F"])

    def test_zero_rate_is_invalid(self):
        with self.assertRaises(ValidationError):
            self.make(hourly_rate=Decimal("0")).full_clean()

    def test_negative_rate_is_invalid(self):
        with self.assertRaises(ValidationError):
            self.make(hourly_rate=Decimal("-5")).full_clean()


class SeedCommandTests(TestCase):
    def test_seed_creates_data_and_is_repeatable(self):
        call_command("seed_equipment", verbosity=0)
        call_command("seed_equipment", verbosity=0)
        self.assertEqual(Zone.objects.count(), 2)
        self.assertEqual(Equipment.objects.count(), 8)
        self.assertTrue(Equipment.objects.filter(is_featured=True).exists())
