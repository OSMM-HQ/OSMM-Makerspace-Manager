from apps.hardware_requests.models import HardwareRequest


def constraint_name(exc):
    diag = getattr(getattr(exc, "__cause__", None), "diag", None)
    return getattr(diag, "constraint_name", "") or ""


def locked_request(request):
    # Nullable FKs must not be select_related under SELECT FOR UPDATE in Postgres.
    return (
        HardwareRequest.objects.select_for_update()
        .select_related("makerspace", "requester")
        .get(pk=request.pk)
    )
