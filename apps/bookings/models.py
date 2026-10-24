from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Func, Q

# Эти статусы занимают время устройства. Отмена, завершение и неявка время освобождают.
BLOCKING_STATUSES = ["confirmed", "in_progress"]


class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class ClubSettings(models.Model):
    """Единственная запись с часами работы клуба (pk всегда 1)."""

    opening_time = models.TimeField("Открытие", default=time(10, 0))
    closing_time = models.TimeField("Закрытие", default=time(23, 0))
    timezone = models.CharField("Часовой пояс", max_length=64, default="Asia/Bishkek")

    class Meta:
        verbose_name = "Настройки клуба"
        verbose_name_plural = "Настройки клуба"

    def __str__(self):
        return "Настройки клуба"

    def clean(self):
        if self.closing_time <= self.opening_time:
            raise ValidationError("Закрытие должно быть позже открытия (работа через полночь не поддерживается).")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValidationError({"timezone": "Неизвестный часовой пояс."})

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def tzinfo(self):
        return ZoneInfo(self.timezone)


class Booking(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Подтверждена"
        IN_PROGRESS = "in_progress", "Идёт"
        COMPLETED = "completed", "Завершена"
        CANCELLED = "cancelled", "Отменена"
        NO_SHOW = "no_show", "Неявка"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings", verbose_name="Клиент"
    )
    equipment = models.ForeignKey(
        "equipment.Equipment", on_delete=models.PROTECT, related_name="bookings", verbose_name="Оборудование"
    )
    start_at = models.DateTimeField("Начало")
    end_at = models.DateTimeField("Окончание")
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    # Тариф и сумма фиксируются в момент создания: изменение каталога не меняет историю.
    rate_snapshot = models.DecimalField("Тариф на момент брони, сом/час", max_digits=8, decimal_places=2)
    total_price = models.DecimalField("Сумма, сом", max_digits=10, decimal_places=2)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        ordering = ["-start_at"]
        verbose_name = "Бронь"
        verbose_name_plural = "Брони"
        indexes = [
            models.Index(fields=["equipment", "start_at"]),
            models.Index(fields=["user", "start_at"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(end_at__gt=F("start_at")), name="booking_end_after_start"),
            models.CheckConstraint(condition=Q(total_price__gte=0), name="booking_total_non_negative"),
            ExclusionConstraint(
                name="booking_no_overlap_per_equipment",
                expressions=[
                    (TsTzRange("start_at", "end_at", RangeBoundary()), RangeOperators.OVERLAPS),
                    ("equipment", RangeOperators.EQUAL),
                ],
                condition=Q(status__in=BLOCKING_STATUSES),
            ),
        ]

    def __str__(self):
        return f"{self.equipment} · {self.start_at:%d.%m.%Y %H:%M}"

    @property
    def duration(self):
        return self.end_at - self.start_at