from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.equipment.models import Equipment, Zone

ZONES = [
    ("Alpha", "ПК / Турниры"),
    ("Bravo", "Консоли / Общая зона"),
]

# (название, зона, тип, характеристики, тариф, на главной, картинка в static/) — демо-данные
EQUIPMENT = [
    ("PC Pro 01", "Alpha", "pc", "RTX 4060\ni5-12400F\n16 GB RAM", "200", True, "images/p-1.png"),
    ("PC Pro 02", "Alpha", "pc", "RTX 4060\ni5-12400F\n16 GB RAM", "200", False, "images/p-2.png"),
    ("PC Elite 01", "Alpha", "pc", "RTX 4070\ni7-13700F\n32 GB RAM", "250", True, "images/e-1.png"),
    ("PC Elite 02", "Alpha", "pc", "RTX 4070\ni7-13700F\n32 GB RAM", "250", False, "images/e-2.png"),
    ("PC Standard 01", "Bravo", "pc", "RTX 3050\ni5-11400F\n16 GB RAM", "150", True, "images/s-1.png"),
    ("PC Standard 02", "Bravo", "pc", "RTX 3050\ni5-11400F\n16 GB RAM", "150", False, "images/s-2.png"),
    ("PlayStation 5", "Bravo", "console", "PS5 Digital\n2 геймпада", "180", True, "images/pl-1.png"),
    ("Xbox Series X", "Bravo", "console", "Xbox Series X\n2 геймпада", "180", False, "images/xb-1.png"),
]


class Command(BaseCommand):
    help = "Заполняет базу демо-зонами и оборудованием. Можно запускать повторно."

    @transaction.atomic
    def handle(self, *args, **options):
        zones = {}
        for name, description in ZONES:
            zone, _ = Zone.objects.update_or_create(name=name, defaults={"description": description})
            zones[name] = zone

        for name, zone_name, kind, specs, rate, featured, image in EQUIPMENT:
            Equipment.objects.update_or_create(
                name=name,
                defaults={
                    "zone": zones[zone_name],
                    "type": kind,
                    "specs": specs,
                    "hourly_rate": Decimal(rate),
                    "is_featured": featured,
                    "image": image,
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"Готово: зон — {Zone.objects.count()}, оборудования — {Equipment.objects.count()}"
        ))