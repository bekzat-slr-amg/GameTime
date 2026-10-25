from datetime import date, datetime, time, timedelta

from django.db.models import Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate

from apps.bookings.models import Booking

ACTIVE_STATUSES = [Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED]
MAX_DAYS = 366


def _parse(value):
    try:
        day = date.fromisoformat(value or "")
    except ValueError:
        return None
    return day if 2000 <= day.year <= 2100 else None


def _hours(value):
    return round(value.total_seconds() / 3600, 1) if value else 0


def parse_range(from_value, to_value, today):
    """Период из формы. Мусор заменяется значениями по умолчанию, период не длиннее года."""
    start = _parse(from_value) or today.replace(day=1)
    end = _parse(to_value) or today
    note = ""
    if end < start:
        start, end = end, start
        note = "Даты были указаны в обратном порядке — мы поменяли их местами."
    if (end - start).days >= MAX_DAYS:
        start = end - timedelta(days=MAX_DAYS - 1)
        note = f"Период ограничен {MAX_DAYS} днями, показан последний отрезок."
    return start, end, note


def build_report(start, end, tz):
    """Брони, начинающиеся с start по end включительно (по часам клуба)."""
    lo = datetime.combine(start, time.min, tzinfo=tz)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
    qs = Booking.objects.filter(start_at__gte=lo, start_at__lt=hi)
    active = qs.filter(status__in=ACTIVE_STATUSES)

    duration = ExpressionWrapper(F("end_at") - F("start_at"), output_field=DurationField())
    revenue = Sum("total_price", filter=Q(status=Booking.Status.COMPLETED))

    totals = active.aggregate(count=Count("id"), hours=Sum(duration), revenue=revenue)

    counts = dict(qs.values_list("status").annotate(n=Count("id")).order_by())
    statuses = [
        {"status": value, "label": label, "count": counts.get(value, 0)}
        for value, label in Booking.Status.choices
    ]

    days = [
        {"day": row["day"], "count": row["count"], "hours": _hours(row["hours"]), "revenue": row["revenue"] or 0}
        for row in active.annotate(day=TruncDate("start_at", tzinfo=tz))
        .values("day")
        .annotate(count=Count("id"), hours=Sum(duration), revenue=revenue)
        .order_by("day")
    ]
    equipment = [
        {"name": row["equipment__name"], "count": row["count"], "hours": _hours(row["hours"]),
         "revenue": row["revenue"] or 0}
        for row in active.values("equipment__name")
        .annotate(count=Count("id"), hours=Sum(duration), revenue=revenue)
        .order_by("equipment__name")
    ]

    return {
        "count": totals["count"],
        "hours": _hours(totals["hours"]),
        "revenue": totals["revenue"] or 0,
        "statuses": statuses,
        "days": days,
        "equipment": equipment,
    }
