from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from apps.apiclients.throttling import ClientTierRateThrottle
from apps.roadmap.models import RoadmapItem
from apps.roadmap.serializers import PublicRoadmapSerializer


@extend_schema(
    tags=["Public roadmap"],
    summary="List public roadmap items",
    description=(
        "List the platform roadmap and changelog items that are published for "
        "public viewing. Descriptions are returned as plain text."
    ),
    auth=[],
    request=None,
    responses=PublicRoadmapSerializer(many=True),
)
class PublicRoadmapListView(ListAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "public_read"
    pagination_class = None
    serializer_class = PublicRoadmapSerializer
    queryset = RoadmapItem.objects.filter(is_public=True).order_by(
        "order",
        "-published_at",
        "id",
    )
