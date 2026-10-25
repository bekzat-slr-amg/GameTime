import secrets
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking, ClubSettings
from apps.bookings.services import price_for_minutes
from apps.equipment.models import Equipment

S = Booking.Status

CLIENTS = [
    ("demo.client1@example.com", "Айбек"),
    ("demo.client2@example.com", "Мээрим"),
    ("demo.client3@example.com", "Тимур"),
]

# (клиент, оборудование, смещение в днях от сегодня, (час, минута), минут, статус)
PLAN = [
    (0, "PC Pro 01", -3, (12, 0), 120, S.COMPLETED),
    (1, "PlayStation 5", -3, (15, 0), 60, S.COMPLETED),
    (2, "PC Elite 01", -3, (18, 0), 60, S.NO_SHOW),
    (1, "PC Pro 02", -2, (14, 0), 60, S.COMPLETED),
    (0, "Xbox Series X", -2, (16, 0), 90, S.COMPLETED),
    (2, "PC Standard 01", -2, (19, 0), 60, S.CANCELLED),
    (2, "PC Elite 02", -1, (13, 0), 120, S.COMPLETED),
    (0, "PlayStation 5", -1, (17, 0), 60, S.COMPLETED),
    (1, "PC Pro 01", -1, (20, 0), 60, S.NO_SHOW),
    (0, "PC Pro 01", 1, (12, 0), 60, S.CONFIRMED),
    (1, "PC Elite 01", 1, (18, 0), 120, S.CONFIRMED),
    (2, "Xbox Series X", 1, (15, 0), 60, S.CANCELLED),
    (1, "PlayStation 5", 2, (19, 0), 90, S.CONFIRMED),
]


class Command(BaseCommand):
    help = "Создаёт демо-клиентов и брони. Можно запускать повторно. Сначала нужен seed_equipment."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Пароль демо-клиентов (по умолчанию случайный, будет показан)")
        parser.add_argument("--force", action="store_true", help="Разрешить запуск при DJANGO_DEBUG=0")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Демо-данные только для разработки (DJANGO_DEBUG=1). Для обхода используйте --force.")

        names = {row[1] for row in PLAN} | {"PC Standard 01", "PC Standard 02"}
        equipment = {e.name: e for e in Equipment.objects.filter(name__in=names)}
        missing = sorted(names - set(equipment))
        if missing:
            raise CommandError(
                f"Нет оборудования: {', '.join(missing)}. Сначала выполните: python manage.py seed_equipment"
            )

        generated = not options["password"]
        password = options["password"] or secrets.token_urlsafe(9)

        users = []
        for email, first_name in CLIENTS:
            user, _ = User.objects.get_or_create(email=email, defaults={"first_name": first_name})
            user.set_password(password)
            user.save()
            users.append(user)

        Booking.objects.filter(user__in=users).delete()

        club = ClubSettings.load()
        tz = club.tzinfo
        now = timezone.now()
        local_now = now.astimezone(tz)
        today = local_now.date()

        rows = []
        for client, name, offset, (hour, minute), minutes, status in PLAN:
            start = datetime.combine(today + timedelta(days=offset), time(hour, minute), tzinfo=tz)
            rows.append((client, name, start, minutes, status))

        # Две брони на сегодня для показа кнопок панели клуба.
        boundary = local_now.replace(minute=0 if local_now.minute < 30 else 30, second=0, microsecond=0)
        rows.append((1, "PC Standard 01", boundary, 60, S.IN_PROGRESS))
        rows.append((2, "PC Standard 02", boundary, 60, S.CONFIRMED))

        created = 0
        for client, name, start, minutes, status in rows:
            end = start + timedelta(minutes=minutes)
            if start.date() != end.date() or start.time() < club.opening_time or end.time() > club.closing_time:
                self.stdout.write(self.style.WARNING(f"Пропущено (вне рабочих часов): {name}, {start:%d.%m %H:%M}"))
                continue
            item = equipment[name]
            Booking.objects.create(
                user=users[client], equipment=item, start_at=start, end_at=end, status=status,
                rate_snapshot=item.hourly_rate, total_price=price_for_minutes(item.hourly_rate, minutes),
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Готово: клиентов — {len(users)}, броней — {created}"))
        self.stdout.write("Демо-клиенты: " + ", ".join(email for email, _ in CLIENTS))
        if generated:
            self.stdout.write(f"Пароль демо-клиентов (показан один раз): {password}")
