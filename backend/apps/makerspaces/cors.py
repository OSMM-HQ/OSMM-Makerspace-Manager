from corsheaders.signals import check_request_enabled

from apps.makerspaces.models import Makerspace, TenantFrontend


def cors_allow_registered_frontend(sender, request, **kwargs):
    origin = request.headers.get("Origin")
    if not origin:
        return False
    for origins in TenantFrontend.objects.filter(is_active=True).values_list("allowed_origins", flat=True):
        if origin in (origins or []):
            return True
    for origins in Makerspace.objects.values_list("cors_allowed_origins", flat=True):
        if origin in (origins or []):
            return True
    return False


def register_signal():
    check_request_enabled.connect(cors_allow_registered_frontend)
