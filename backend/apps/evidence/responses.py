from rest_framework import status
from rest_framework.response import Response


def storage_unavailable_response(detail="Storage is unavailable."):
    return Response(
        {"detail": detail, "code": "storage_unavailable"},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )