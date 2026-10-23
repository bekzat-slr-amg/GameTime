from django.db.models import Count, Min, Q
from django.shortcuts import render

from apps.equipment.models import Equipment, Zone

FEATURES = [
    {"icon": "monitor", "title": "PC / PS5", "text": "Современное оборудование"},
    {"icon": "clock", "title": "30 мин", "text": "Шаг бронирования"},
    {"icon": "globe", "title": "Online", "text": "Выбор времени"},
    {"icon": "shield", "title": "Безопасность", "text": "Защита данных"},
    {"icon": "headset", "title": "Поддержка", "text": "Всегда на связи"},
]


def home(request):
    available = Equipment.objects.filter(is_active=True, zone__is_active=True).select_related("zone")

    tariffs = [
        {"label": Equipment.Type(row["type"]).label, "min_rate": row["min_rate"]}
        for row in available.values("type").annotate(min_rate=Min("hourly_rate")).order_by("type")
    ]
    zones = Zone.objects.filter(is_active=True).annotate(
        places=Count("equipment", filter=Q(equipment__is_active=True))
    ).order_by("name")

    return render(request, "core/home.html", {
        "features": FEATURES,
        "equipment": available.filter(is_featured=True)[:4],
        "zones": zones,
        "tariffs": tariffs,
    })