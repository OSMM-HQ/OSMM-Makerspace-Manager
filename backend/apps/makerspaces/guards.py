from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from apps.makerspaces.models import Makerspace
from apps.makerspaces.platform import feature_enabled, module_enabled


def require_module(makerspace_or_id, module_key):
    makerspace = (
        makerspace_or_id
        if isinstance(makerspace_or_id, Makerspace)
        else get_object_or_404(Makerspace, pk=makerspace_or_id)
    )
    if not module_enabled(makerspace, module_key):
        raise ValidationError({"module": f"{module_key} is disabled for this makerspace."})
    return makerspace


def require_feature(makerspace_or_id, feature_key):
    makerspace = (
        makerspace_or_id
        if isinstance(makerspace_or_id, Makerspace)
        else get_object_or_404(Makerspace, pk=makerspace_or_id)
    )
    if not feature_enabled(makerspace, feature_key):
        raise ValidationError({"feature": f"{feature_key} is disabled for this makerspace."})
    return makerspace
