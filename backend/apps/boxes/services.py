from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.boxes.models import QrCode
from apps.hardware_requests.self_checkout_workflow import qr_has_active_loan


def revoke_qr_code(actor, qr):
    if qr.status == QrCode.Status.REVOKED:
        raise ValidationError("QR code is already revoked.")
    if qr_has_active_loan(qr.makerspace, qr):
        raise ValidationError("Cannot revoke a QR code with an outstanding loan.")

    qr.status = QrCode.Status.REVOKED
    qr.revoked_at = timezone.now()
    qr.save(update_fields=["status", "revoked_at", "updated_at"])
    audit.record(actor, "qr.revoked", makerspace=qr.makerspace, target=qr)
    return qr
