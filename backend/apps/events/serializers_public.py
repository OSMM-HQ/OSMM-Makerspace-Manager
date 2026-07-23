from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.events.capacity import availability_label
from apps.events.models import Event, EventRegistration
from apps.forms_schema.serializers import CustomFormSubmissionMixin


PUBLIC_EVENT_FIELDS = (
    'public_token',
    'title',
    'description',
    'starts_at',
    'ends_at',
    'location',
    'location_kind',
    'custom_form',
    'capacity',
    'availability',
    'status',
)


class PublicEventSerializer(serializers.Serializer):
    public_token = serializers.UUIDField(read_only=True)
    title = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    starts_at = serializers.DateTimeField(read_only=True)
    ends_at = serializers.DateTimeField(read_only=True)
    location = serializers.CharField(read_only=True)
    location_kind = serializers.ChoiceField(
        choices=Event.LocationKind.choices,
        read_only=True,
    )
    custom_form = serializers.JSONField(allow_null=True, read_only=True)
    capacity = serializers.IntegerField(min_value=0, read_only=True)
    availability = serializers.SerializerMethodField()
    status = serializers.ChoiceField(
        choices=[Event.Status.PUBLISHED],
        read_only=True,
    )

    @extend_schema_field(
        {
            'type': 'string',
            'enum': ['Available', 'Limited', 'Full'],
        }
    )
    def get_availability(self, obj):
        return availability_label(obj)


class PublicEventRegistrationInputSerializer(
    CustomFormSubmissionMixin,
    serializers.Serializer,
):
    def custom_form_schema(self):
        return self.context['event'].custom_form


class PublicEventRegistrationResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(
            EventRegistration.Status.REGISTERED,
            EventRegistration.Status.WAITLISTED,
        ),
        read_only=True,
    )
