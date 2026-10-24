from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class ClubAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Только вошедший пользователь с ролью «Администратор клуба». Клиент получает 403."""

    def test_func(self):
        return self.request.user.is_club_admin

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied
        return super().handle_no_permission()