from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.equipment.models import Equipment

from .models import BLOCKING_STATUSES, Booking, ClubSettings

STEP = timedelta(minutes=30)


class BookingError(Exception):
    """Нарушено правило бронирования. Текст можно показывать пользователю."""


def calc_price(rate, start_at, end_at):
    minutes = Decimal((end_at - start_at) // timedelta(minutes=1))
    return (rate * minutes / Decimal(60)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def has_overlap(equipment, start_at, end_at):
    """Интервалы полуоткрытые [start, end): соседние брони не пересекаются."""
    return Booking.objects.filter(
        equipment=equipment,
        status__in=BLOCKING_STATUSES,
        start_at__lt=end_at,
        end_at__gt=start_at,
    ).exists()


def validate_interval(start_at, end_at, club, now):
    if timezone.is_naive(start_at) or timezone.is_naive(end_at):
        raise BookingError("Некорректное время.")
    if start_at <= now:
        raise BookingError("Время начала должно быть в будущем.")
    if end_at <= start_at:
        raise BookingError("Время окончания должно быть позже начала.")

    duration = end_at - start_at
    if duration < STEP:
        raise BookingError("Минимальная длительность брони — 30 минут.")
    if duration % STEP != timedelta(0):
        raise BookingError("Длительность должна быть кратна 30 минутам.")

    tz = club.tzinfo
    local_start = start_at.astimezone(tz)
    local_end = end_at.astimezone(tz)

    if local_start.minute % 30 != 0 or local_start.second or local_start.microsecond:
        raise BookingError("Начало должно быть на границе получаса (например, 12:00 или 12:30).")
    if local_start.date() != local_end.date():
        raise BookingError("Бронь не может переходить через полночь.")
    if local_start.time() < club.opening_time or local_end.time() > club.closing_time:
        raise BookingError(
            f"Клуб работает с {club.opening_time:%H:%M} до {club.closing_time:%H:%M}."
        )


def create_booking(*, user, equipment_id, start_at, end_at, now=None):
    """Создаёт бронь атомарно. Цену считает сервер, браузеру не доверяем."""
    now = now or timezone.now()
    club = ClubSettings.load()
    try:
        with transaction.atomic():
            # Блокируем строку устройства: параллельные брони на него выстраиваются в очередь.
            try:
                equipment = (
                    Equipment.objects.select_for_update(of=("self",))
                    .select_related("zone")
                    .get(pk=equipment_id)
                )
            except Equipment.DoesNotExist:
                raise BookingError("Оборудование не найдено.")

            if not equipment.is_active or not equipment.zone.is_active:
                raise BookingError("Это оборудование сейчас недоступно для брони.")

            validate_interval(start_at, end_at, club, now)

            if has_overlap(equipment, start_at, end_at):
                raise BookingError("Это время уже занято. Выберите другой интервал.")

            return Booking.objects.create(
                user=user,
                equipment=equipment,
                start_at=start_at,
                end_at=end_at,
                rate_snapshot=equipment.hourly_rate,
                total_price=calc_price(equipment.hourly_rate, start_at, end_at),
            )
    except IntegrityError:
        # Последняя линия защиты: сработало ограничение PostgreSQL на пересечение.
        raise BookingError("Это время уже занято. Выберите другой интервал.")