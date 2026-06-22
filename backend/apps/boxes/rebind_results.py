from dataclasses import dataclass

from apps.boxes.models import QrCode


@dataclass(frozen=True)
class QrRebindResult:
    qr: QrCode
