from django.urls import path

from apps.integrations import views
from apps.integrations.views_push import PushDeviceDetailView, PushDeviceListCreateView

urlpatterns = [
    path("push/devices", PushDeviceListCreateView.as_view(), name="push-device-list-create"),
    path("push/devices/<int:device_id>", PushDeviceDetailView.as_view(), name="push-device-detail"),
    path("telegram/webhook", views.TelegramWebhookView.as_view(), name="telegram-webhook"),
    path("telegram/test-alert", views.TelegramTestAlertView.as_view(), name="telegram-test-alert"),
]
