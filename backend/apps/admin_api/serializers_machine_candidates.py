from rest_framework import serializers

from apps.makerspaces.models import MakerspaceMembership


class OperatorCandidateSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = MakerspaceMembership
        fields = ['user_id', 'username', 'display_name']
        read_only_fields = fields

    def get_display_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
