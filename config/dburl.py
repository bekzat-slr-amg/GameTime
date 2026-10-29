from urllib.parse import parse_qsl, unquote, urlparse

ALLOWED_OPTIONS = ("sslmode", "channel_binding")


def parse_database_url(url):
    """Разбирает строку подключения PostgreSQL (Neon) в настройки Django."""
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ValueError("DATABASE_URL должен начинаться с postgresql://")
    if not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("В DATABASE_URL нет хоста или имени базы")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(parsed.port or 5432),
        "OPTIONS": {k: v for k, v in parse_qsl(parsed.query) if k in ALLOWED_OPTIONS},
    }
