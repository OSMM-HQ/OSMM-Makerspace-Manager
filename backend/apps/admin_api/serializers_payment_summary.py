from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from apps.accounts import rbac
from apps.payments.models import Payment


class StaffPaymentSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ("id", "status", "amount", "currency")
        read_only_fields = fields


class PaymentSummaryMixin:
    @extend_schema_field(StaffPaymentSummarySerializer(allow_null=True))
    def get_payment(self, obj):
        payment = self.context.get("payments_by_subject_id", {}).get(obj.pk)
        if payment is None:
            return None
        return StaffPaymentSummarySerializer(payment).data


def scoped_payment_context(actor, action, subject_type, subject_ids):
    payments = rbac.scope_by_action(
        actor,
        action,
        Payment.objects.filter(
            subject_type=subject_type,
            subject_id__in=list(subject_ids),
        ),
        field="makerspace_id",
    )
    return {
        "payments_by_subject_id": {
            payment.subject_id: payment for payment in payments
        }
    }
