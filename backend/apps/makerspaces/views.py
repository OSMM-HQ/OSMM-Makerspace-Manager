from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.makerspaces.platform import bootstrap_payload, resolve_frontend


class BootstrapView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Tenant bootstrap"],
        summary="Resolve tenant and frontend-safe configuration",
        parameters=[
            OpenApiParameter("tenant", str, OpenApiParameter.QUERY),
            OpenApiParameter("slug", str, OpenApiParameter.QUERY),
        ],
        responses={
            200: OpenApiResponse(description="Frontend-safe tenant bootstrap payload."),
            404: OpenApiResponse(description="No active tenant frontend matched."),
        },
    )
    def get(self, request, *args, **kwargs):
        frontend = resolve_frontend(
            tenant=request.query_params.get("tenant"),
            slug=request.query_params.get("slug"),
            origin=request.headers.get("Origin"),
            host=request.get_host(),
        )
        if frontend is None:
            return Response(
                {"detail": "No active tenant frontend matched."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(bootstrap_payload(frontend))
