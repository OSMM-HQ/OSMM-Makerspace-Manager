from django.urls import path

from apps.notifications.views import (
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
    NotificationUnreadCountView,
)

app_name = "notifications"

urlpatterns = [
    path(
        "makerspace/<int:makerspace_id>",
        NotificationListView.as_view(),
        name="notifications-list",
    ),
    path(
        "makerspace/<int:makerspace_id>/unread-count",
        NotificationUnreadCountView.as_view(),
        name="notifications-unread-count",
    ),
    path(
        "makerspace/<int:makerspace_id>/read-all",
        NotificationMarkAllReadView.as_view(),
        name="notifications-read-all",
    ),
    path(
        "makerspace/<int:makerspace_id>/<int:pk>/read",
        NotificationMarkReadView.as_view(),
        name="notifications-read",
    ),
]