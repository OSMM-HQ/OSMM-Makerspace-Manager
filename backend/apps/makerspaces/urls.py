from django.urls import path

from apps.makerspaces.config_views import PublicConfigView
from apps.makerspaces.views import BootstrapView

urlpatterns = [
    path("bootstrap", BootstrapView.as_view(), name="tenant-bootstrap"),
    path("config", PublicConfigView.as_view(), name="public-config"),
]
