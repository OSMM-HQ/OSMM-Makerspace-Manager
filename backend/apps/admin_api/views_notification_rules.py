from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff
from apps.audit import services as audit
from apps.integrations import notification_rules
from apps.integrations.models import EmailNotificationMute
from apps.makerspaces.models import Makerspace


class NotificationRuleCatalogItemSerializer(serializers.Serializer):
    stream = serializers.CharField()
    audience = serializers.CharField()
    targets = serializers.ListField(child=serializers.CharField())
    events = serializers.ListField(child=serializers.CharField())


class NotificationRuleMuteSerializer(serializers.Serializer):
    target = serializers.CharField()
    stream = serializers.CharField()
    event = serializers.CharField()
    audience = serializers.CharField()


class NotificationRulesResponseSerializer(serializers.Serializer):
    catalog = NotificationRuleCatalogItemSerializer(many=True)
    mutes = NotificationRuleMuteSerializer(many=True)


class NotificationRuleChangeSerializer(serializers.Serializer):
    target = serializers.CharField()
    stream = serializers.CharField()
    event = serializers.CharField()
    audience = serializers.CharField()
    muted = serializers.BooleanField()


class NotificationRulesPatchSerializer(serializers.Serializer):
    changes = NotificationRuleChangeSerializer(many=True)


@extend_schema(tags=["Makerspaces"], summary="List or update makerspace email notification rules")
class NotificationRulesView(APIView):
    permission_classes = [IsActiveStaff]
    http_method_names = ["get", "patch", "head", "options"]

    def _makerspace(self, request, makerspace_id):
        return get_object_or_404(
            rbac.scope_by_action(
                request.user,
                rbac.Action.MANAGE_MAKERSPACE,
                Makerspace.objects.filter(archived_at__isnull=True),
                field="id",
            ),
            pk=makerspace_id,
        )

    def _catalog(self):
        catalog = []
        for (stream, audience), events in notification_rules.EVENT_CATALOG.items():
            targets = [
                target
                for target in notification_rules.valid_targets_for_stream(stream)
                if notification_rules.TARGETS.get(target) == audience
            ]
            catalog.append(
                {
                    "stream": stream,
                    "audience": audience,
                    "targets": targets,
                    "events": list(events),
                }
            )
        return catalog

    def _response_data(self, makerspace):
        mutes = list(
            EmailNotificationMute.objects.filter(makerspace=makerspace)
            .order_by("stream", "audience", "target", "event")
            .values("target", "stream", "event", "audience")
        )
        return {"catalog": self._catalog(), "mutes": mutes}

    def _validation_error(self, change):
        target = change["target"]
        stream = change["stream"]
        event = change["event"]
        audience = change["audience"]
        expected_audience = notification_rules.TARGETS.get(target)
        if audience != expected_audience:
            return f"Invalid audience '{audience}' for target '{target}'."
        if target not in notification_rules.valid_targets_for_stream(stream):
            return f"Invalid target '{target}' for stream '{stream}'."
        if not notification_rules.is_event_mutable(stream, audience, event):
            return f"Event '{event}' is not mutable for stream '{stream}' and audience '{audience}'."
        return None

    @extend_schema(responses={200: NotificationRulesResponseSerializer})
    def get(self, request, makerspace_id, *args, **kwargs):
        makerspace = self._makerspace(request, makerspace_id)
        return Response(self._response_data(makerspace), status=status.HTTP_200_OK)

    @extend_schema(
        request=NotificationRulesPatchSerializer,
        responses={
            200: NotificationRulesResponseSerializer,
            400: OpenApiResponse(description="Invalid notification rule change."),
            404: OpenApiResponse(description="Makerspace not found."),
        },
    )
    def patch(self, request, makerspace_id, *args, **kwargs):
        makerspace = self._makerspace(request, makerspace_id)
        payload = NotificationRulesPatchSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        changes = payload.validated_data["changes"]

        applied = []
        with transaction.atomic():
            desired_states = {}
            for change in changes:
                error = self._validation_error(change)
                if error:
                    return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
                key = (
                    change["target"],
                    change["stream"],
                    change["event"],
                    change["audience"],
                )
                desired_states[key] = change["muted"]

            for (target, stream, event, audience), muted in desired_states.items():
                if muted:
                    _, created = EmailNotificationMute.objects.get_or_create(
                        makerspace=makerspace,
                        target=target,
                        stream=stream,
                        event=event,
                        defaults={"audience": audience, "created_by": request.user},
                    )
                    changed = created
                else:
                    deleted_count, _ = EmailNotificationMute.objects.filter(
                        makerspace=makerspace,
                        target=target,
                        stream=stream,
                        event=event,
                        audience=audience,
                    ).delete()
                    changed = deleted_count > 0
                if changed:
                    applied.append(
                        {
                            "target": target,
                            "stream": stream,
                            "event": event,
                            "audience": audience,
                            "muted": muted,
                        }
                    )

            if applied:
                audit.record(
                    request.user,
                    "email.notification_rules_updated",
                    makerspace=makerspace,
                    target=makerspace,
                    meta={"changes": applied},
                )

        return Response(self._response_data(makerspace), status=status.HTTP_200_OK)
