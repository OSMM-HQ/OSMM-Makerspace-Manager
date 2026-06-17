from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics

from apps.makerspaces.guards import require_module
from apps.printing.models import PrintBucket
from apps.printing.permissions import IsActiveRequester
from apps.printing.serializers import PrintBucketSerializer
from apps.printing.views_common import ERROR_RESPONSES, _int_query_param


@extend_schema(tags=["Printing"], summary="List active print buckets")
class PrintBucketListView(generics.ListAPIView):
    permission_classes = [IsActiveRequester]
    serializer_class = PrintBucketSerializer
    pagination_class = None

    def get_queryset(self):
        makerspace_id = _int_query_param(self.request, "makerspace", required=True)
        require_module(makerspace_id, "printing")
        return PrintBucket.objects.filter(
            makerspace_id=makerspace_id,
            makerspace__archived_at__isnull=True,
            is_active=True,
        ).order_by("name")

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="makerspace",
                type=int,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Makerspace id whose active buckets should be listed.",
            ),
        ],
        responses={200: PrintBucketSerializer(many=True), **ERROR_RESPONSES},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
