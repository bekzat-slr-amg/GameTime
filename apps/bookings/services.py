from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.equipment.models import Equipment

from .models import BLOCKING_STATUSES, Booking, ClubSettings

STEP = timedelta(minutes=30)
MAX_DAYS_AHEAD = 30
DURATION_CHOICES = [(30, "30 мин"), (60, "1 час"), (90, "1 ч 30 мин"), (120, "2 часа")]
DURATIONS = [minutes for minutes, _ in DURATION_CHOICES]
DEFAULT_DURATION = 60


class BookingError(Exception):
    """Нарушено правило бронирования. Текст можно показывать пользователю."""


def price_for_minutes(rate, minutes):
    return (rate * Decimal(minutes) / Decimal(60)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calc_price(rate, start_at, end_at):
    return price_for_minutes(rate, (end_at - start_at) // timedelta(minutes=1))


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
    if local_start.date() > now.astimezone(tz).date() + timedelta(days=MAX_DAYS_AHEAD):
        raise BookingError(f"Бронь возможна не более чем на {MAX_DAYS_AHEAD} дней вперёд.")
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


# ---- Выбор времени на странице устройства ----

def parse_day(value, club, now):
    """Дата из формы: не раньше сегодняшней (по часам клуба) и не дальше MAX_DAYS_AHEAD."""
    try:
        day = date.fromisoformat(value or "")
    except ValueError:
        return None
    today = now.astimezone(club.tzinfo).date()
    if day < today or day > today + timedelta(days=MAX_DAYS_AHEAD):
        return None
    return day


def parse_duration(value):
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DURATION
    return minutes if minutes in DURATIONS else DEFAULT_DURATION


def day_slots(equipment, day, duration_minutes, now=None):
    """Слоты начала брони на день. state: free / busy / past / outside."""
    now = now or timezone.now()
    club = ClubSettings.load()
    tz = club.tzinfo
    duration = timedelta(minutes=duration_minutes)
    opens = datetime.combine(day, club.opening_time, tzinfo=tz)
    closes = datetime.combine(day, club.closing_time, tzinfo=tz)

    busy = list(
        Booking.objects.filter(
            equipment=equipment, status__in=BLOCKING_STATUSES, start_at__lt=closes, end_at__gt=opens
        ).values_list("start_at", "end_at")
    )

    slots = []
    start = opens
    while start + STEP <= closes:
        end = start + duration
        if start <= now:
            state = "past"
        elif end > closes:
            state = "outside"
        elif any(start < b_end and end > b_start for b_start, b_end in busy):
            state = "busy"
        else:
            state = "free"
        slots.append({"label": start.strftime("%H:%M"), "end_label": end.strftime("%H:%M"), "state": state})
        start += STEP
    return slots


def slots_context(equipment, day_value, duration_value, now=None):
    now = now or timezone.now()
    club = ClubSettings.load()
    today = now.astimezone(club.tzinfo).date()
    duration = parse_duration(duration_value)
    day = parse_day(day_value, club, now) if day_value else today

    slots = day_slots(equipment, day, duration, now=now) if day is not None else []
    return {
        "today": today,
        "max_day": today + timedelta(days=MAX_DAYS_AHEAD),
        "day": day or today,
        "day_valid": day is not None,
        "duration": duration,
        "durations": DURATION_CHOICES,
        "opening": club.opening_time,
        "closing": club.closing_time,
        "price": price_for_minutes(equipment.hourly_rate, duration),
        "slots": slots,
        "has_free": any(slot["state"] == "free" for slot in slots),
    }

def cancel_booking(*, booking_id, user, now=None):
    """Отмена своей брони до начала. Чужая бронь не находится (как будто её нет)."""
    now = now or timezone.now()
    with transaction.atomic():
        try:
            booking = Booking.objects.select_for_update().get(pk=booking_id, user=user)
        except Booking.DoesNotExist:
            raise BookingError("Бронь не найдена.")

        if booking.status != Booking.Status.CONFIRMED:
            raise BookingError("Эту бронь уже нельзя отменить.")
        if booking.start_at <= now:
            raise BookingError("Сеанс уже начался, отмена невозможна.")

        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
        return booking