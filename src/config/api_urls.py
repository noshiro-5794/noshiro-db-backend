from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns = [
    path("", include("apps.index.api.urls")),
    path("", include("apps.users.api.urls")),
    path("", include("apps.community.api.urls")),
    path("", include("apps.sync.api.urls")),
    path("openapi/", SpectacularAPIView.as_view(), name="openapi-schema"),
]
