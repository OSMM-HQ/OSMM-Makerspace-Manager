from rest_framework.exceptions import ValidationError

from apps.makerspaces.models import Makerspace
from apps.makerspaces.platform import module_enabled


def require_module(makerspace_or_id, module_key):
    makerspace = (
        makerspace_or_id
        if isinstance(makerspace_or_id, Makerspace)
        else Makerspace.objects.get(pk=makerspace_or_id)
    )
    if not module_enabled(makerspace, module_key):
        raise ValidationError({"module": f"{module_key} is disabled for this makerspace."})
    return makerspace
