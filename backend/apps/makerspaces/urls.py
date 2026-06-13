from django.urls import path

from apps.makerspaces.views import BootstrapView

urlpatterns = [
    path("bootstrap", BootstrapView.as_view(), name="tenant-bootstrap"),
]
