from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("admin/", admin.site.urls),
    path("api/", include("apps.inventory.urls")),          # existing, unchanged
    # Versioned alias of the public routes. Namespaced so it does NOT collide with the
    # unnamespaced names above — reverse("public-inventory") stays /api/public/...,
    # while /api/v1/public/... is reachable directly (and via "v1:public-inventory").
    path("api/v1/", include(("apps.inventory.urls", "inventory"), namespace="v1")),
    path("api/v1/auth/", include("apps.accounts.urls")),   # staff auth surface
    path("api/v1/admin/", include("apps.evidence.urls")),
    path("api/v1/printing/", include("apps.printing.urls")),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
