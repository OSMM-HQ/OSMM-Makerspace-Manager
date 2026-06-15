from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts import rbac
from apps.makerspaces.guards import require_module
from apps.printing import workflow
from apps.printing.models import FilamentSpool, PrintBucket, PrintPrinter, PrintRequest
from apps.printing.permissions import CanManagePrinting, IsActiveRequester
from apps.printing.serializers import (
    ErrorSerializer,
    FilamentSpoolSerializer,
    PrintBucketSerializer,
    PrintPrinterSerializer,
    PrintRequestCreateSerializer,
    PrintRequestSerializer,
    PrintStartSerializer,
    RejectFailSerializer,
)
from apps.printing.views_buckets import PrintBucketListView
from apps.printing.views_common import ACTION_RESPONSES, ERROR_RESPONSES, _int_query_param
from apps.printing.views_printers import (
    ManagedPrinterDetailView,
    ManagedPrinterListCreateView,
    ManagedPrinterMixin,
)
from apps.printing.views_requests import (
    ManagedPrintFileUrlView,
    ManagedPrintRequestDetailView,
    ManagedPrintRequestListView,
    ManagedPrintRequestQuerysetMixin,
    PrintRequestCreateListView,
    PrintRequestDetailView,
    PrintedListView,
)
from apps.printing.views_request_actions import (
    PrintRequestAcceptView,
    PrintRequestActionView,
    PrintRequestCompleteView,
    PrintRequestFailView,
    PrintRequestRejectView,
    PrintRequestStartView,
)
from apps.printing.views_spools import (
    ManagedFilamentSpoolDetailView,
    ManagedFilamentSpoolListCreateView,
)

__all__ = [
    "ACTION_RESPONSES",
    "CanManagePrinting",
    "ERROR_RESPONSES",
    "ErrorSerializer",
    "FilamentSpool",
    "FilamentSpoolSerializer",
    "IsActiveRequester",
    "ManagedFilamentSpoolDetailView",
    "ManagedFilamentSpoolListCreateView",
    "ManagedPrintFileUrlView",
    "ManagedPrintRequestDetailView",
    "ManagedPrintRequestListView",
    "ManagedPrintRequestQuerysetMixin",
    "ManagedPrinterDetailView",
    "ManagedPrinterListCreateView",
    "ManagedPrinterMixin",
    "OpenApiParameter",
    "OpenApiResponse",
    "PrintBucket",
    "PrintBucketListView",
    "PrintBucketSerializer",
    "PrintPrinter",
    "PrintPrinterSerializer",
    "PrintRequest",
    "PrintRequestAcceptView",
    "PrintRequestActionView",
    "PrintRequestCompleteView",
    "PrintRequestCreateListView",
    "PrintRequestCreateSerializer",
    "PrintRequestDetailView",
    "PrintRequestFailView",
    "PrintRequestRejectView",
    "PrintRequestSerializer",
    "PrintRequestStartView",
    "PrintStartSerializer",
    "PrintedListView",
    "RejectFailSerializer",
    "Response",
    "ValidationError",
    "_int_query_param",
    "extend_schema",
    "generics",
    "rbac",
    "require_module",
    "status",
    "workflow",
]
