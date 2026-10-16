from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/v1/batches/", include("apps.batches.urls")),
    path("api/v1/worksheets/", include("apps.workflow.urls")),
    path("", include("apps.dashboard.urls")),
]

