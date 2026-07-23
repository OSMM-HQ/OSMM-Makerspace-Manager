from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.admin_api.permissions import IsActiveStaff
from apps.admin_api.serializers_notification_rules import (
    NotificationRulesPatchSerializer,
    NotificationRulesResponseSerializer,
)
from apps.audit import services as audit
from apps.integrations import notification_catalog, notification_rules
from apps.integrations.models import (
    EmailNotificationMute,
    NotificationChannel,
    NotificationFeature,
    NotificationPreference,
)
from apps.makerspaces.models import Makerspace


@extend_schema(tags=["Makerspaces"], summary="List or update makerspace notification rules")
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
        # Load every override row ONCE (feature, channel -> enabled) and resolve each of
        # the 20 cells in memory. Calling is_notification_enabled per cell would issue 20
        # serial NotificationPreference queries on every GET/PATCH response.
        override_rows = {
            (feature, channel): enabled
            for feature, channel, enabled in NotificationPreference.objects.filter(
                makerspace=makerspace
            ).values_list("feature", "channel", "enabled")
        }
        channels = [
            {"key": channel.value, "label": channel.label}
            for channel in NotificationChannel
        ]
        features = [
            {
                "key": feature.value,
                "label": feature.label,
                "events": list(notification_catalog.FEATURE_EVENTS[feature]),
            }
            for feature in NotificationFeature
        ]
        preferences = [
            {
                "feature": feature.value,
                "channel": channel.value,
                "enabled": override_rows.get(
                    (feature.value, channel.value),
                    notification_catalog.default_state(feature, channel),
                ),
                "source": (
                    "override"
                    if (feature.value, channel.value) in override_rows
                    else "default"
                ),
            }
            for feature in NotificationFeature
            for channel in NotificationChannel
        ]
        return {
            "catalog": self._catalog(),
            "mutes": mutes,
            "channels": channels,
            "features": features,
            "preferences": preferences,
        }

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
            400: OpenApiResponse(description="Invalid notification rule or preference change."),
            404: OpenApiResponse(description="Makerspace not found."),
        },
    )
    def patch(self, request, makerspace_id, *args, **kwargs):
        makerspace = self._makerspace(request, makerspace_id)
        payload = NotificationRulesPatchSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        changes = payload.validated_data.get("changes", [])
        preference_changes = payload.validated_data.get("preferences", [])

        desired_mutes = {}
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
            desired_mutes[key] = change["muted"]

        desired_preferences = {}
        for preference in preference_changes:
            key = (preference["feature"], preference["channel"])
            desired_preferences[key] = preference["enabled"]

        applied = []
        with transaction.atomic():
            for (target, stream, event, audience), muted in desired_mutes.items():
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

            applied_preferences = []
            for (feature, channel), enabled in desired_preferences.items():
                NotificationPreference.objects.update_or_create(
                    makerspace=makerspace,
                    feature=feature,
                    channel=channel,
                    defaults={"enabled": enabled, "updated_by": request.user},
                )
                applied_preferences.append(
                    {"feature": feature, "channel": channel, "enabled": enabled}
                )

            if applied:
                audit.record(
                    request.user,
                    "email.notification_rules_updated",
                    makerspace=makerspace,
                    target=makerspace,
                    meta={"changes": applied},
                )
            if applied_preferences:
                audit.record(
                    request.user,
                    "notification.preferences_updated",
                    makerspace=makerspace,
                    target=makerspace,
                    meta={"preferences": applied_preferences},
                )

        return Response(self._response_data(makerspace), status=status.HTTP_200_OK)
