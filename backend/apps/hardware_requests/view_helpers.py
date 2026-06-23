from drf_spectacular.utils import OpenApiResponse

from apps.hardware_requests.exceptions import ErrorSerializer
from apps.hardware_requests.models import HardwareRequest

ERROR_400 = OpenApiResponse(ErrorSerializer, description="Invalid request.")
ERROR_403 = OpenApiResponse(ErrorSerializer, description="Permission denied.")
ERROR_404 = OpenApiResponse(ErrorSerializer, description="Not found.")
ERROR_409 = OpenApiResponse(ErrorSerializer, description="Workflow conflict.")
ERROR_503 = OpenApiResponse(ErrorSerializer, description="Service unavailable.")

PUBLIC_ERROR_RESPONSES = {
    400: ERROR_400,
    403: ERROR_403,
    404: ERROR_404,
    503: ERROR_503,
}
ADMIN_LIST_ERROR_RESPONSES = {
    403: ERROR_403,
    404: ERROR_404,
}
ACTION_ERROR_RESPONSES = {
    400: ERROR_400,
    403: ERROR_403,
    404: ERROR_404,
    409: ERROR_409,
}


def request_queryset():
    return HardwareRequest.objects.select_related(
        "makerspace",
        "requester",
        "accepted_by",
        "assigned_box",
        "issued_by",
        "issue_evidence",
    ).prefetch_related("items__product", "items__asset_links__asset", "returnevent_set")
