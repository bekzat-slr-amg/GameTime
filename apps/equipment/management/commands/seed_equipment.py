from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.equipment.models import Equipment, Zone

ZONES = [
    ("Alpha", "ПК / Турниры"),
    ("Bravo", "Консоли / Общая зона"),
]

# (название, зона, тип, характеристики, тариф, на главной) — демо-данные
EQUIPMENT = [
    ("PC Pro 01", "Alpha", "pc", "RTX 4060\ni5-12400F\n16 GB RAM", "200", True),
    ("PC Pro 02", "Alpha", "pc", "RTX 4060\ni5-12400F\n16 GB RAM", "200", False),
    ("PC Elite 01", "Alpha", "pc", "RTX 4070\ni7-13700F\n32 GB RAM", "250", True),
    ("PC Elite 02", "Alpha", "pc", "RTX 4070\ni7-13700F\n32 GB RAM", "250", False),
    ("PC Standard 01", "Bravo", "pc", "RTX 3050\ni5-11400F\n16 GB RAM", "150", True),
    ("PC Standard 02", "Bravo", "pc", "RTX 3050\ni5-11400F\n16 GB RAM", "150", False),
    ("PlayStation 5", "Bravo", "console", "PS5 Digital\n2 геймпада", "180", True),
    ("Xbox Series X", "Bravo", "console", "Xbox Series X\n2 геймпада", "180", False),
]


class Command(BaseCommand):
    help = "Заполняет базу демо-зонами и оборудованием. Можно запускать повторно."

    @transaction.atomic
    def handle(self, *args, **options):
        zones = {}
        for name, description in ZONES:
            zone, _ = Zone.objects.update_or_create(name=name, defaults={"description": description})
            zones[name] = zone

        for name, zone_name, kind, specs, rate, featured in EQUIPMENT:
            Equipment.objects.update_or_create(
                name=name,
                defaults={
                    "zone": zones[zone_name],
                    "type": kind,
                    "specs": specs,
                    "hourly_rate": Decimal(rate),
                    "is_featured": featured,
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"Готово: зон — {Zone.objects.count()}, оборудования — {Equipment.objects.count()}"
        ))