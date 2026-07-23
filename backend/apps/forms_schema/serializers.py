from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.forms_schema.validation import validate_answers, validate_form_schema


class CustomFormSchemaField(serializers.JSONField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            return validate_form_schema(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class CustomFormSubmissionMixin(metaclass=serializers.SerializerMetaclass):
    custom_answers = serializers.JSONField(
        allow_null=True,
        required=False,
        write_only=True,
    )

    def custom_form_schema(self):
        raise NotImplementedError

    def validate(self, attrs):
        attrs = super().validate(attrs)
        attrs['custom_answers'] = validate_answers(
            self.custom_form_schema(), attrs.get('custom_answers')
        )
        return attrs
