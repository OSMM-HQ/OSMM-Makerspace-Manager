from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import exception_handler
from drf_spectacular.utils import extend_schema_serializer

from apps.bookings.exceptions import BookingConflict, BookingInvalidTransition
from apps.checkin.client import CheckinDenied, CheckinUnavailable
from apps.evidence.storage import StorageUnavailable
from apps.events.exceptions import (
    CapacityConflict,
    DuplicateRegistration,
    EventInvalidTransition,
)
from apps.hardware_requests.workflow import (
    BoxUnavailable,
    BoxValidationError,
    EvidenceNotUploaded,
    InvalidTransition,
    RequesterBlocked,
    RequestValidationError,
    ReturnValidationError,
)
from apps.inventory.availability import InsufficientStock
from apps.maintenance.exceptions import (
    InactiveMaintenanceSchedule,
    MaintenanceStatusConflict,
    RetiredMachineMaintenance,
)


@extend_schema_serializer(component_name="HardwareRequestError")
class ErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()
    code = serializers.CharField()


_EXCEPTION_MAP = {
    RetiredMachineMaintenance: (
        status.HTTP_409_CONFLICT,
        "machine_retired",
        "Machine is retired.",
    ),
    InactiveMaintenanceSchedule: (
        status.HTTP_409_CONFLICT,
        "maintenance_schedule_inactive",
        "Maintenance schedule is inactive.",
    ),
    MaintenanceStatusConflict: (
        status.HTTP_409_CONFLICT,
        "maintenance_status_conflict",
        "Only a machine in maintenance can be set to idle.",
    ),
    RequesterBlocked: (
        status.HTTP_403_FORBIDDEN,
        "requester_blocked",
        "Requester is blocked.",
    ),
    CheckinDenied: (
        status.HTTP_403_FORBIDDEN,
        "checkin_denied",
        "Check-in was denied.",
    ),
    CheckinUnavailable: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "checkin_unavailable",
        "Check-in service is unavailable.",
    ),
    InvalidTransition: (
        status.HTTP_409_CONFLICT,
        "invalid_transition",
        "Invalid request transition.",
    ),
    EventInvalidTransition: (
        status.HTTP_409_CONFLICT,
        "invalid_transition",
        "Invalid event transition.",
    ),
    BookingInvalidTransition: (
        status.HTTP_409_CONFLICT,
        "invalid_transition",
        "Invalid booking transition.",
    ),
    BookingConflict: (
        status.HTTP_409_CONFLICT,
        "booking_conflict",
        "This space is already booked for that time.",
    ),
    CapacityConflict: (
        status.HTTP_409_CONFLICT,
        "capacity_conflict",
        "Event capacity conflicts with confirmed registrations.",
    ),
    DuplicateRegistration: (
        status.HTTP_400_BAD_REQUEST,
        "duplicate_registration",
        "A registration already exists for this email.",
    ),
    InsufficientStock: (
        status.HTTP_409_CONFLICT,
        "insufficient_stock",
        "Insufficient stock.",
    ),
    RequestValidationError: (
        status.HTTP_400_BAD_REQUEST,
        "validation_error",
        "Invalid request.",
    ),
    ReturnValidationError: (
        status.HTTP_400_BAD_REQUEST,
        "return_validation_error",
        "Invalid return.",
    ),
    BoxValidationError: (
        status.HTTP_400_BAD_REQUEST,
        "box_validation_error",
        "Invalid box.",
    ),
    BoxUnavailable: (
        status.HTTP_409_CONFLICT,
        "box_unavailable",
        "Box is already out on another loan.",
    ),
    EvidenceNotUploaded: (
        status.HTTP_409_CONFLICT,
        "evidence_not_uploaded",
        "Evidence has not been uploaded.",
    ),
    StorageUnavailable: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "evidence_storage_unavailable",
        "Evidence storage is unavailable.",
    ),
}


def workflow_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response

    for exc_type, (status_code, code, default_detail) in _EXCEPTION_MAP.items():
        if isinstance(exc, exc_type):
            detail = str(exc) or default_detail
            return Response(
                {"detail": detail, "code": code},
                status=status_code,
            )

    return None
