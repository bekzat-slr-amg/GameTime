# GameTime

Веб-сервис бронирования игрового клуба. Семестровый проект.

**Стек:** Django 5.2, PostgreSQL 17, Django Templates, Tailwind CSS 4, HTMX, Docker Compose.

## Требования

- Docker Desktop (с запущенным движком)
- Git

## Запуск

    git clone <адрес репозитория>
    cd GameTime
    copy .env.example .env

Открой `.env` и задай свои значения `DJANGO_SECRET_KEY` и `POSTGRES_PASSWORD`.
Ключ можно сгенерировать так:

    python -c "import secrets; print(secrets.token_urlsafe(50))"

Затем:

    docker compose up -d --build
    docker compose exec web python manage.py migrate

Сайт откроется на http://localhost:8000

## Сервисы

- `web` — Django (порт 8000)
- `db` — PostgreSQL
- `tailwind` — сборка CSS из `static/src/input.css` в `static/css/styles.css`

## Полезные команды

    docker compose ps
    docker compose logs web --tail 30
    docker compose exec web python manage.py check
    docker compose down

## Текущее состояние

Готово: инфраструктура (Docker, PostgreSQL), базовая оболочка, главная страница.
Контакты, адрес, тарифы и оборудование на главной — демо-значения.
Авторизация, каталог и бронирование ещё не реализованы.
