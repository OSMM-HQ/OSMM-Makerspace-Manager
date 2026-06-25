from rest_framework import serializers

from apps.makerspaces.models import Makerspace
from apps.printing.models import (
    FilamentSpool,
    ManualPrintLog,
    PrintBucket,
    PrintPrinter,
    PrintRequest,
)
from apps.printing.serializers_buckets import ErrorSerializer, PrintBucketSerializer
from apps.printing.serializers_manual_logs import ManualPrintLogSerializer
from apps.printing.serializers_printers import PrintPrinterSerializer
from apps.printing.serializers_requests import (
    CompletePrintSerializer,
    FailPrintSerializer,
    ManagedPrintRequestSerializer,
    PrintAcceptSerializer,
    PrintRequestCreateSerializer,
    PrintRequestSerializer,
    PrintStartSerializer,
    RejectFailSerializer,
)
from apps.printing.serializers_spools import (
    FilamentSpoolSerializer,
    FilamentSpoolSummarySerializer,
)

__all__ = [
    "CompletePrintSerializer",
    "ErrorSerializer",
    "FilamentSpool",
    "FailPrintSerializer",
    "FilamentSpoolSerializer",
    "FilamentSpoolSummarySerializer",
    "ManualPrintLog",
    "ManualPrintLogSerializer",
    "ManagedPrintRequestSerializer",
    "Makerspace",
    "PrintBucket",
    "PrintBucketSerializer",
    "PrintPrinter",
    "PrintPrinterSerializer",
    "PrintAcceptSerializer",
    "PrintRequest",
    "PrintRequestCreateSerializer",
    "PrintRequestSerializer",
    "PrintStartSerializer",
    "RejectFailSerializer",
    "serializers",
]
