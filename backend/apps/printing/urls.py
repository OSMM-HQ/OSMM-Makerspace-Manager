from django.urls import path

from apps.printing.views import (
    ManagedPrintRequestDetailView,
    ManagedPrintRequestListView,
    PrintBucketListView,
    PrintRequestAcceptView,
    PrintRequestCompleteView,
    PrintRequestCreateListView,
    PrintRequestDetailView,
    PrintRequestFailView,
    PrintRequestRejectView,
    PrintRequestStartView,
    PrintedListView,
)

app_name = "printing"

urlpatterns = [
    path("requests/", PrintRequestCreateListView.as_view(), name="request-list"),
    path("requests/<int:pk>/", PrintRequestDetailView.as_view(), name="request-detail"),
    path("buckets/", PrintBucketListView.as_view(), name="bucket-list"),
    path(
        "manage/requests/",
        ManagedPrintRequestListView.as_view(),
        name="managed-request-list",
    ),
    path(
        "manage/requests/<int:pk>/",
        ManagedPrintRequestDetailView.as_view(),
        name="managed-request-detail",
    ),
    path(
        "manage/requests/<int:pk>/accept",
        PrintRequestAcceptView.as_view(),
        name="managed-request-accept",
    ),
    path(
        "manage/requests/<int:pk>/reject",
        PrintRequestRejectView.as_view(),
        name="managed-request-reject",
    ),
    path(
        "manage/requests/<int:pk>/start",
        PrintRequestStartView.as_view(),
        name="managed-request-start",
    ),
    path(
        "manage/requests/<int:pk>/complete",
        PrintRequestCompleteView.as_view(),
        name="managed-request-complete",
    ),
    path(
        "manage/requests/<int:pk>/fail",
        PrintRequestFailView.as_view(),
        name="managed-request-fail",
    ),
    path("manage/printed/", PrintedListView.as_view(), name="printed-list"),
]
