from rest_framework import serializers

from apps.machines.models import MachineServiceRequest
from apps.payments.models import Payment


class MemberPaymentSerializer(serializers.ModelSerializer):
    subject_label = serializers.SerializerMethodField()
    checkout_url = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ("id", "subject_type", "subject_label", "status", "checkout_url", "created_at")

    def get_subject_label(self, payment) -> str:
        labels = self.context.get("payment_subject_labels", {})
        if label := labels.get(payment.subject_id):
            return label
        if payment.subject_type == Payment.SubjectType.MACHINE_SERVICE_REQUEST:
            return MachineServiceRequest.objects.filter(pk=payment.subject_id).values_list("title", flat=True).first() or "Machine service"
        return "Payment"

    def get_checkout_url(self, payment) -> str:
        return payment.stripe_checkout_url if payment.status == Payment.Status.PENDING else ""


class CheckoutUrlSerializer(serializers.Serializer):
    checkout_url = serializers.URLField()


class StaffPaymentSerializer(MemberPaymentSerializer):
    class Meta(MemberPaymentSerializer.Meta):
        fields = MemberPaymentSerializer.Meta.fields + ("amount", "currency")

