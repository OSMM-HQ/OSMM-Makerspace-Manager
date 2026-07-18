from rest_framework import serializers
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field

from apps.presence.models import PresenceSession


class PresenceStartSerializer(serializers.Serializer):
    duration_minutes = serializers.IntegerField(min_value=15, max_value=480)


class PresenceSessionSerializer(serializers.ModelSerializer):
    active = serializers.SerializerMethodField()

    class Meta:
        model = PresenceSession
        fields = ["started_at", "expires_at", "ended_at", "end_reason", "active"]

    @extend_schema_field(serializers.BooleanField)
    def get_active(self, obj):
        return obj.ended_at is None and obj.expires_at > timezone.now()


class PresenceCurrentSerializer(serializers.Serializer):
    active = serializers.BooleanField()
    session = PresenceSessionSerializer(allow_null=True)


class PresenceRosterSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source="member.display_name")
    role_label = serializers.SerializerMethodField()

    class Meta:
        model = PresenceSession
        fields = ["display_name", "role_label", "started_at", "expires_at"]

    @extend_schema_field(serializers.CharField)
    def get_role_label(self, obj):
        role = obj.membership.assigned_role
        return role.name if role else obj.membership.get_role_display()
