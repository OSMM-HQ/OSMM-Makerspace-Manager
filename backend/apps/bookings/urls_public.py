from django.urls import path

from apps.bookings.views_public import (
    PublicBookableSpaceListView,
    PublicBookingSubmissionView,
    PublicSpaceAvailabilityView,
)


urlpatterns = [
    path(
        '<slug:makerspace_slug>/spaces/',
        PublicBookableSpaceListView.as_view(),
        name='public-bookable-space-list',
    ),
    path(
        '<slug:makerspace_slug>/spaces/<uuid:public_token>/availability/',
        PublicSpaceAvailabilityView.as_view(),
        name='public-space-availability',
    ),
    path(
        '<slug:makerspace_slug>/spaces/<uuid:public_token>/book/',
        PublicBookingSubmissionView.as_view(),
        name='public-booking-submit',
    ),
]
