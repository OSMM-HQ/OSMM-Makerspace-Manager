from django.conf import settings
from django.http import Http404
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.hardware_requests.services_return_reminders import run_return_reminders


ReturnReminderCronResponseSerializer = inline_serializer(
    name="ReturnReminderCronResponse",
    fields={
        "sent": serializers.IntegerField(),
        "skipped": serializers.IntegerField(),
    },
)


class ReturnReminderCronView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        tags=["Health"],
        auth=[],
        request=None,
        responses={
            200: OpenApiResponse(
                response=ReturnReminderCronResponseSerializer,
                description="Return reminder run result.",
            ),
            403: OpenApiResponse(description="Invalid cron secret."),
            404: OpenApiResponse(description="Cron endpoint is not configured."),
        },
    )
    def post(self, request):
        secret = settings.CRON_SECRET
        if not secret:
            raise Http404()
        provided = request.headers.get("X-Cron-Secret", "")
        import secrets as _secrets

        if not _secrets.compare_digest(provided, secret):
            return Response(status=403)
        result = run_return_reminders()
        return Response(result, status=200)
