from django.urls import path

from apps.inventory.views import (
    PublicCategoryListView,
    PublicInventoryDetailView,
    PublicInventoryListView,
    PublicMakerspaceListView,
)
from apps.inventory.views_public_stats import PublicMakerspaceStatsView

urlpatterns = [
    path(
        "public/makerspaces/",
        PublicMakerspaceListView.as_view(),
        name="public-makerspaces",
    ),
    path(
        "public/<slug:makerspace_slug>/inventory/",
        PublicInventoryListView.as_view(),
        name="public-inventory",
    ),
    path(
        "public/<slug:makerspace_slug>/stats/",
        PublicMakerspaceStatsView.as_view(),
        name="public-makerspace-stats",
    ),
    path(
        "public/<slug:makerspace_slug>/inventory/categories/",
        PublicCategoryListView.as_view(),
        name="public-inventory-categories",
    ),
    path(
        "public/<slug:makerspace_slug>/inventory/<int:pk>/",
        PublicInventoryDetailView.as_view(),
        name="public-inventory-detail",
    ),
]
