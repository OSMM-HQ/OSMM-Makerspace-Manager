from rest_framework import serializers

from apps.payments.models import Payment
from apps.payments.subjects import subject_label


class PaymentReconciliationSerializer(serializers.ModelSerializer):
    subject_label = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "id",
            "subject_type",
            "subject_id",
            "subject_label",
            "status",
            "amount",
            "currency",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_subject_label(self, payment):
        return subject_label(
            payment,
            self.context.get("payment_subject_labels", {}),
        )


class PaymentListFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Payment.Status.choices, required=False)
    subject_type = serializers.ChoiceField(
        choices=Payment.SubjectType.choices, required=False
    )


class PaymentBulkActionSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False
    )

    def validate_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Payment IDs must be unique.")
        return value
