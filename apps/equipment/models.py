from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Zone(models.Model):
    name = models.CharField("Название", max_length=50, unique=True)
    description = models.CharField("Описание", max_length=200, blank=True)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Зона"
        verbose_name_plural = "Зоны"

    def __str__(self):
        return self.name


class Equipment(models.Model):
    class Type(models.TextChoices):
        PC = "pc", "ПК"
        CONSOLE = "console", "Консоль"

    zone = models.ForeignKey(Zone, on_delete=models.PROTECT, related_name="equipment", verbose_name="Зона")
    name = models.CharField("Название", max_length=80, unique=True)
    type = models.CharField("Тип", max_length=20, choices=Type.choices)
    specs = models.TextField("Характеристики", blank=True, help_text="Каждая характеристика с новой строки")
    hourly_rate = models.DecimalField(
        "Тариф, сом/час",
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    image = models.CharField(
        "Путь к изображению",
        max_length=200,
        blank=True,
        help_text="Относительно static/, например images/pc-pro-01.jpg",
    )
    is_active = models.BooleanField("Доступно для брони", default=True)
    is_featured = models.BooleanField("Показывать на главной", default=False)

    class Meta:
        ordering = ["zone__name", "name"]
        verbose_name = "Оборудование"
        verbose_name_plural = "Оборудование"
        indexes = [models.Index(fields=["type", "is_active"])]

    def __str__(self):
        return self.name

    @property
    def specs_list(self):
        return [line.strip() for line in self.specs.splitlines() if line.strip()]