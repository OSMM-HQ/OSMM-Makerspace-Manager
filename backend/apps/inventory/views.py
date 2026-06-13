from django.db.models import Q
from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from apps.inventory.serializers import (
    PublicMakerspaceSerializer,
    PublicProductSerializer,
)
from apps.makerspaces.models import Makerspace
from apps.makerspaces.lookup import get_public_makerspace
from apps.makerspaces.platform import module_enabled
from apps.openapi import PUBLISHABLE_KEY_PARAMETER


@extend_schema(
    tags=["Public inventory"],
    summary="List public makerspaces",
    description="List makerspaces that have public inventory enabled.",
    parameters=[PUBLISHABLE_KEY_PARAMETER],
    responses=PublicMakerspaceSerializer(many=True),
)
class PublicMakerspaceListView(ListAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_read"
    serializer_class = PublicMakerspaceSerializer
    pagination_class = None

    def get_queryset(self):
        return Makerspace.objects.filter(
            public_inventory_enabled=True,
        ).order_by("name")


@extend_schema(
    tags=["Public inventory"],
    summary="List public inventory products",
    description="List public inventory products for a public makerspace.",
    parameters=[
        PUBLISHABLE_KEY_PARAMETER,
        OpenApiParameter(
            name="makerspace_slug",
            type=str,
            location=OpenApiParameter.PATH,
            description="Public makerspace code (for example TSEL) or slug.",
        ),
        OpenApiParameter(
            name="q",
            type=str,
            location=OpenApiParameter.QUERY,
            description="Search public products by name or description.",
        ),
    ],
    responses=PublicProductSerializer(many=True),
)
class PublicInventoryListView(ListAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_read"
    serializer_class = PublicProductSerializer

    def get_queryset(self):
        makerspace = get_public_makerspace(self.kwargs["makerspace_slug"])
        if not makerspace.public_inventory_enabled or not module_enabled(makerspace, "public_inventory"):
            raise Http404

        queryset = makerspace.products.filter(
            is_public=True,
            is_archived=False,
        )
        query = self.request.query_params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            )

        return queryset.order_by("name")


@extend_schema(
    tags=["Public inventory"],
    summary="Get public inventory product detail",
    parameters=[PUBLISHABLE_KEY_PARAMETER],
    responses=PublicProductSerializer,
)
class PublicInventoryDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_read"
    serializer_class = PublicProductSerializer

    def get_queryset(self):
        makerspace = get_public_makerspace(self.kwargs["makerspace_slug"])
        if not makerspace.public_inventory_enabled or not module_enabled(makerspace, "public_inventory"):
            raise Http404
        return makerspace.products.filter(is_public=True, is_archived=False).order_by("name")
