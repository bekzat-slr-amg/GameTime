from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("equipment/", include("apps.equipment.urls")),
    path("bookings/", include("apps.bookings.urls")),
    path("club/", include("apps.club.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# ---- Продакшен ----
from django.http import HttpResponse  # noqa: E402
from django.urls import re_path  # noqa: E402
from django.views.static import serve  # noqa: E402

urlpatterns += [path("healthz/", lambda request: HttpResponse("ok"), name="healthz")]

if settings.SERVE_MEDIA and not settings.DEBUG:
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]
