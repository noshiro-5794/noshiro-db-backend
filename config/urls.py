from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/index/", include("apps.index.api.urls")),
    path("api/community/", include("apps.community.api.urls")),
    path("api/sync/", include("apps.sync.api.urls")),
    path("api/users/", include("apps.users.api.urls")),
]
