# ER-диаграмма GameTime

```mermaid
erDiagram
    USER ||--o{ BOOKING : "делает"
    ZONE ||--o{ EQUIPMENT : "содержит"
    EQUIPMENT ||--o{ BOOKING : "бронируется"

    USER {
        bigint id PK
        string email UK "логин"
        string first_name
        string phone
        string role "client | club_admin"
        string password "хеш Django"
    }
    ZONE {
        bigint id PK
        string name UK
        string description
        bool is_active
    }
    EQUIPMENT {
        bigint id PK
        bigint zone_id FK
        string name UK
        string type "pc | console"
        text specs
        decimal hourly_rate "сом/час"
        string photo "файл в media/equipment/"
        string image "демо-путь в static/"
        bool is_active
        bool is_featured
    }
    BOOKING {
        bigint id PK
        bigint user_id FK
        bigint equipment_id FK
        timestamptz start_at
        timestamptz end_at
        string status "confirmed | in_progress | completed | cancelled | no_show"
        decimal rate_snapshot "тариф на момент брони"
        decimal total_price "сумма на момент брони"
        timestamptz created_at
        timestamptz updated_at
    }
    CLUB_SETTINGS {
        int id PK "всегда 1"
        time opening_time
        time closing_time
        string timezone
    }
```

## Связи

- Один пользователь делает много броней. Удалить пользователя с бронями нельзя (`PROTECT`): история сохраняется.
- Зона содержит много единиц оборудования. Зону с оборудованием удалить нельзя.
- Единица оборудования бронируется много раз. Оборудование с бронями удалить нельзя, его выключают флагом `is_active`.
- `CLUB_SETTINGS` не связана с другими таблицами: единственная запись (id = 1) с часами работы клуба и его часовым поясом.

## Ограничения в базе

- `end_at > start_at` (CheckConstraint).
- `total_price >= 0` (CheckConstraint).
- Бронь одного устройства не пересекается с другой активной бронью: `ExclusionConstraint` на PostgreSQL (расширение `btree_gist`). Учитываются статусы `confirmed` и `in_progress`. Отменённые, завершённые и неявки время не занимают.
- `email` пользователя, `name` зоны и `name` оборудования уникальны.
- Индексы: `(equipment, start_at)`, `(user, start_at)`, `(type, is_active)`.

## Деньги и время

- Деньги хранятся как `Decimal`, валюта интерфейса — сом (KGS).
- Время хранится в UTC (`timestamptz`), показывается и считается в часовом поясе клуба.
- Тариф и сумма фиксируются в брони при создании, изменение каталога не меняет историю.
