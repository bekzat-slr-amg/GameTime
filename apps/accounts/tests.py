from django.test import TestCase
from django.urls import reverse

from .models import User

PASSWORD = "Str0ng-pass-2026"


def make_user(email="client@example.com", **kwargs):
    return User.objects.create_user(email=email, password=PASSWORD, first_name="Тест", **kwargs)


class RegistrationTests(TestCase):
    def setUp(self):
        self.url = reverse("accounts:register")

    def data(self, **extra):
        data = {
            "first_name": "Амин",
            "email": "new@example.com",
            "phone": "+996 700 000 000",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "agree": "on",
        }
        data.update(extra)
        return data

    def test_register_creates_client_and_logs_in(self):
        response = self.client.post(self.url, self.data())
        self.assertRedirects(response, reverse("core:home"))
        user = User.objects.get(email="new@example.com")
        self.assertEqual(user.role, User.Role.CLIENT)
        self.assertFalse(user.is_staff)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_role_and_staff_flags_in_post_are_ignored(self):
        self.client.post(self.url, self.data(role="club_admin", is_staff="on", is_superuser="on"))
        user = User.objects.get(email="new@example.com")
        self.assertEqual(user.role, User.Role.CLIENT)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_duplicate_email_is_rejected_case_insensitive(self):
        make_user("new@example.com")
        response = self.client.post(self.url, self.data(email="NEW@example.com"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "уже существует")
        self.assertEqual(User.objects.count(), 1)

    def test_password_mismatch_is_rejected(self):
        self.client.post(self.url, self.data(password2="Other-pass-2026"))
        self.assertEqual(User.objects.count(), 0)

    def test_weak_password_is_rejected(self):
        self.client.post(self.url, self.data(password1="12345678", password2="12345678"))
        self.assertEqual(User.objects.count(), 0)

    def test_agreement_is_required(self):
        data = self.data()
        del data["agree"]
        self.client.post(self.url, data)
        self.assertEqual(User.objects.count(), 0)


class LoginTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.url = reverse("accounts:login")

    def test_login_success(self):
        response = self.client.post(self.url, {"username": "client@example.com", "password": PASSWORD})
        self.assertRedirects(response, reverse("core:home"))
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_login_email_is_case_insensitive(self):
        self.client.post(self.url, {"username": "CLIENT@Example.com", "password": PASSWORD})
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_wrong_password_does_not_log_in(self):
        response = self.client.post(self.url, {"username": "client@example.com", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_session_expires_on_close_without_remember_me(self):
        self.client.post(self.url, {"username": "client@example.com", "password": PASSWORD})
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_remember_me_keeps_session(self):
        self.client.post(
            self.url, {"username": "client@example.com", "password": PASSWORD, "remember_me": "on"}
        )
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_logged_in_user_is_redirected_from_login(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_logout_requires_post_and_logs_out(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.url = reverse("accounts:profile")

    def test_profile_requires_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={self.url}", fetch_redirect_response=False
        )

    def test_profile_opens_for_logged_in_user(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_profile_update_saves_name_and_phone(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {"first_name": "Новое", "phone": "+996 555 123 456"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Новое")
        self.assertEqual(self.user.phone, "+996 555 123 456")

    def test_profile_cannot_change_email_or_role(self):
        self.client.force_login(self.user)
        self.client.post(
            self.url,
            {"first_name": "Тест", "phone": "", "email": "hacker@example.com", "role": "club_admin"},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "client@example.com")
        self.assertEqual(self.user.role, User.Role.CLIENT)

    def test_profile_rejects_invalid_phone(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {"first_name": "Тест", "phone": "abc"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "")


class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.url = reverse("accounts:password")

    def test_password_page_requires_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={self.url}", fetch_redirect_response=False
        )

    def test_password_change_works_and_keeps_session(self):
        self.client.force_login(self.user)
        new = "Another-pass-2027"
        response = self.client.post(
            self.url, {"old_password": PASSWORD, "new_password1": new, "new_password2": new}
        )
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)

    def test_wrong_old_password_does_not_change_password(self):
        self.client.force_login(self.user)
        new = "Another-pass-2027"
        self.client.post(self.url, {"old_password": "wrong", "new_password1": new, "new_password2": new})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))


class RoleTests(TestCase):
    def test_default_role_is_client(self):
        user = make_user()
        self.assertEqual(user.role, User.Role.CLIENT)
        self.assertFalse(user.is_club_admin)

    def test_superuser_is_club_admin(self):
        admin = User.objects.create_superuser(email="boss@example.com", password=PASSWORD)
        self.assertTrue(admin.is_club_admin)
        self.assertTrue(admin.is_staff)

    def test_user_without_email_is_not_created(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password=PASSWORD)

    def test_client_cannot_open_django_admin(self):
        self.client.force_login(make_user())
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/admin/login/"))