from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


def docs_root(_request):
    return HttpResponse(
        """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>OSMM API</title>
    <script>
      window.location.replace(window.location.hash ? "/redoc/" : "/docs/");
    </script>
    <noscript>
      <meta http-equiv="refresh" content="0; url=/docs/">
      <a href="/docs/">Open Swagger UI</a>
      <a href="/redoc/">Open Redoc</a>
    </noscript>
  </head>
  <body></body>
</html>""",
        content_type="text/html",
    )


urlpatterns = [
    path("", docs_root, name="docs-root"),
    # Mounted at /control/ (not /admin/) so it never collides with the React staff
    # console, which owns /admin on the SPA. The Django admin is the Super Admin
    # control plane and lives on its own dedicated prefix.
    path("control/", admin.site.urls),
    path("api/", include("apps.inventory.urls")),          # existing, unchanged
    # Versioned alias of the public routes. Namespaced so it does NOT collide with the
    # unnamespaced names above — reverse("public-inventory") stays /api/public/...,
    # while /api/v1/public/... is reachable directly (and via "v1:public-inventory").
    path("api/v1/", include(("apps.inventory.urls", "inventory"), namespace="v1")),
    path("api/v1/", include("apps.makerspaces.urls")),
    path("api/v1/", include("apps.hardware_requests.urls")),
    path("api/v1/auth/", include("apps.accounts.urls")),   # staff auth surface
    path("api/v1/admin/", include("apps.admin_api.urls")),
    path("api/v1/admin/", include("apps.boxes.urls")),
    path("api/v1/admin/", include("apps.evidence.urls")),
    path("api/v1/", include("apps.operations.urls")),
    path("api/v1/integrations/", include("apps.integrations.urls")),
    path("api/v1/printing/", include("apps.printing.urls")),
    path("api/v1/procurement/", include("apps.procurement.urls")),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="api-redoc-ui",
    ),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]
