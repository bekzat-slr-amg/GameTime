from django.shortcuts import render

# Демо-данные для главной. На этапе «оборудование» заменим запросом к модели Equipment.
FEATURES = [
    {"icon": "monitor", "title": "PC / PS5", "text": "Современное оборудование"},
    {"icon": "clock", "title": "30 мин", "text": "Шаг бронирования"},
    {"icon": "globe", "title": "Online", "text": "Выбор времени"},
    {"icon": "shield", "title": "Безопасность", "text": "Защита данных"},
    {"icon": "headset", "title": "Поддержка", "text": "Всегда на связи"},
]

DEMO_EQUIPMENT = [
    {"type": "PC", "name": "PC Pro 01", "zone": "Зона Alpha", "specs": ["RTX 4060", "i5-12400F", "16 GB RAM"], "price": 200, "image": None},
    {"type": "PS5", "name": "PlayStation 5", "zone": "Зона Bravo", "specs": ["PS5 Digital", "2 геймпада"], "price": 180, "image": None},
    {"type": "PC", "name": "PC Elite", "zone": "Зона Alpha", "specs": ["RTX 4070", "i7-13700F", "32 GB RAM"], "price": 250, "image": None},
    {"type": "PC", "name": "PC Standard", "zone": "Зона Bravo", "specs": ["RTX 4060", "i5-11400F", "16 GB RAM"], "price": 150, "image": None},
]


def home(request):
    return render(request, "core/home.html", {
        "features": FEATURES,
        "equipment": DEMO_EQUIPMENT,
    })