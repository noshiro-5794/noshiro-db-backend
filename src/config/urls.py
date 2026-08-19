from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularSwaggerView

from config.health import liveness, readiness


def optional_urlpatterns():
    patterns = []
    if settings.ENABLE_ADMIN:
        patterns.append(path("admin/", admin.site.urls))
    if settings.ENABLE_API_DOCS:
        patterns.append(
            path(
                "api/docs/",
                SpectacularSwaggerView.as_view(url_name="openapi-schema"),
                name="api-docs",
            )
        )
    return patterns


urlpatterns = [
    path("health/live/", liveness, name="health-live"),
    path("health/ready/", readiness, name="health-ready"),
    path("api/v1/", include("config.api_urls")),
    *optional_urlpatterns(),
]
