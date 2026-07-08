from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = (
            "id",
            "level",
            "event",
            "title",
            "body",
            "url_path",
            "read_at",
            "created_at",
        )
        read_only_fields = fields