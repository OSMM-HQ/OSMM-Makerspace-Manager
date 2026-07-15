from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.inventory import public_image_storage
from apps.machines import services


class PublicMachineTypeSerializer(serializers.Serializer):
    name = serializers.CharField(read_only=True)
    icon = serializers.CharField(read_only=True)


class PublicMachineSerializer(serializers.Serializer):
    '''Allowlist-only public projection; never subclass the staff serializer.'''

    name = serializers.CharField(read_only=True)
    machine_type = PublicMachineTypeSerializer(read_only=True)
    image_url = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)
    usage_hours = serializers.SerializerMethodField()

    @extend_schema_field({'type': 'string', 'format': 'uri', 'nullable': True})
    def get_image_url(self, machine):
        return public_image_storage.public_url(machine.image_key) or None

    @extend_schema_field(
        {'type': 'string', 'format': 'decimal', 'example': '12.50'}
    )
    def get_usage_hours(self, machine):
        total = getattr(machine, 'usage_total', None)
        if total is None:
            total = services.machine_usage_total(machine)
        return f'{total:.2f}'
