from rest_framework import serializers

from apps.roadmap.models import RoadmapItem


class PublicRoadmapSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoadmapItem
        fields = (
            "title",
            "description",
            "status",
            "category",
            "published_at",
        )
        read_only_fields = fields
