from django.urls import path

from apps.events.views_public import (
    PublicEventListView,
    PublicEventRegistrationView,
)


urlpatterns = [
    path(
        '<slug:makerspace_slug>/events/',
        PublicEventListView.as_view(),
        name='public-event-list',
    ),
    path(
        '<slug:makerspace_slug>/events/<uuid:public_token>/register/',
        PublicEventRegistrationView.as_view(),
        name='public-event-register',
    ),
]
