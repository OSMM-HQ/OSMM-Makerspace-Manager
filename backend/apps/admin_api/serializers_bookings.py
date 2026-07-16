from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.bookings import storage
from apps.bookings.exceptions import BookerNamesRequiresAvailability
from apps.bookings.models import BookableSpace, Booking


class BookableSpaceWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    kind = serializers.ChoiceField(
        choices=BookableSpace.Kind.choices,
        default=BookableSpace.Kind.OTHER,
        required=False,
    )
    description = serializers.CharField(allow_blank=True, default='', required=False)
    capacity = serializers.IntegerField(default=0, min_value=0, required=False)
    location = serializers.CharField(
        allow_blank=True,
        default='',
        max_length=255,
        required=False,
    )
    is_public = serializers.BooleanField(default=False, required=False)
    show_public_availability = serializers.BooleanField(default=False, required=False)
    show_public_booker_names = serializers.BooleanField(default=False, required=False)

    def validate(self, attrs):
        availability = attrs.get(
            'show_public_availability',
            getattr(self.instance, 'show_public_availability', False),
        )
        names = attrs.get(
            'show_public_booker_names',
            getattr(self.instance, 'show_public_booker_names', False),
        )
        if names and not availability:
            raise BookerNamesRequiresAvailability()
        return attrs


class BookableSpaceAdminSerializer(serializers.ModelSerializer):
    makerspace_id = serializers.IntegerField(read_only=True)
    created_by_id = serializers.IntegerField(allow_null=True, read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = BookableSpace
        fields = (
            'id',
            'public_token',
            'makerspace_id',
            'name',
            'kind',
            'description',
            'capacity',
            'location',
            'image_url',
            'is_public',
            'show_public_availability',
            'show_public_booker_names',
            'is_active',
            'created_by_id',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_image_url(self, obj):
        return storage.public_url(obj.image_key)


class BookingAdminSerializer(serializers.ModelSerializer):
    space_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Booking
        fields = (
            'id',
            'public_token',
            'space_id',
            'name',
            'email',
            'phone',
            'starts_at',
            'ends_at',
            'status',
            'note',
            'created_at',
        )
        read_only_fields = fields


class SpaceImagePresignRequestSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=255)
    content_type = serializers.CharField(max_length=100)


class SpaceImageUploadSerializer(serializers.Serializer):
    url = serializers.URLField()
    method = serializers.ChoiceField(choices=('PUT',), required=False)
    fields = serializers.DictField(required=False)
    headers = serializers.DictField(required=False)


class SpaceImagePresignResponseSerializer(serializers.Serializer):
    object_key = serializers.CharField()
    upload = SpaceImageUploadSerializer()


class SpaceImageFinalizeRequestSerializer(serializers.Serializer):
    object_key = serializers.CharField(max_length=500)


class EmptyActionSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if data:
            raise serializers.ValidationError(
                {field: 'Unexpected field.' for field in data}
            )
        return value


class BookableSpaceListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True, required=False)
    previous = serializers.CharField(allow_null=True, required=False)
    results = BookableSpaceAdminSerializer(many=True)


class BookingListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True, required=False)
    previous = serializers.CharField(allow_null=True, required=False)
    results = BookingAdminSerializer(many=True)


class BookingListFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Booking.Status.choices, required=False)
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        if (
            attrs.get('starts_at')
            and attrs.get('ends_at')
            and attrs['ends_at'] < attrs['starts_at']
        ):
            raise serializers.ValidationError(
                {'ends_at': 'End of window must be at or after its start.'}
            )
        return attrs
