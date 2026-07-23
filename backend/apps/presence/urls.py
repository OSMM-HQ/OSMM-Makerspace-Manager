from django.urls import path

from apps.presence.views import PresenceCurrentView, PresenceEndView, PresenceStartView


urlpatterns = [
    path("<slug:makerspace_slug>/presence-sessions", PresenceStartView.as_view(), name="presence-start"),
    path("<slug:makerspace_slug>/presence-sessions/current", PresenceCurrentView.as_view(), name="presence-current"),
    path("<slug:makerspace_slug>/presence-sessions/current/end", PresenceEndView.as_view(), name="presence-end"),
]
