from django.test import SimpleTestCase, TestCase

from .dburl import parse_database_url


class ParseDatabaseUrlTests(SimpleTestCase):
    def test_neon_style_url(self):
        cfg = parse_database_url(
            "postgresql://neondb_owner:secret@ep-cool-123.eu-central-1.aws.neon.tech/neondb?sslmode=require"
        )
        self.assertEqual(cfg["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(cfg["NAME"], "neondb")
        self.assertEqual(cfg["USER"], "neondb_owner")
        self.assertEqual(cfg["PASSWORD"], "secret")
        self.assertEqual(cfg["HOST"], "ep-cool-123.eu-central-1.aws.neon.tech")
        self.assertEqual(cfg["PORT"], "5432")
        self.assertEqual(cfg["OPTIONS"], {"sslmode": "require"})

    def test_percent_encoded_credentials_are_decoded(self):
        cfg = parse_database_url("postgresql://us%40er:p%40ss%2Fword%3A1@host.example/db")
        self.assertEqual(cfg["USER"], "us@er")
        self.assertEqual(cfg["PASSWORD"], "p@ss/word:1")

    def test_explicit_port(self):
        self.assertEqual(parse_database_url("postgresql://u:p@host.example:6543/db")["PORT"], "6543")

    def test_only_known_options_are_passed(self):
        cfg = parse_database_url("postgresql://u:p@host.example/db?sslmode=require&channel_binding=require&evil=1")
        self.assertEqual(cfg["OPTIONS"], {"sslmode": "require", "channel_binding": "require"})

    def test_postgres_scheme_is_accepted(self):
        self.assertEqual(parse_database_url("postgres://u:p@host.example/db")["NAME"], "db")

    def test_invalid_urls_raise(self):
        for url in ("mysql://u:p@host.example/db", "postgresql://u:p@host.example/", "postgresql:///db", "garbage"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    parse_database_url(url)


class HealthCheckTests(TestCase):
    def test_healthz_is_public_and_returns_ok(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")
