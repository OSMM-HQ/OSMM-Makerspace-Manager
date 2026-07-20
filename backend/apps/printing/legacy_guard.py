"""Read-only fence for retained B4 compatibility tables."""

from django.core.exceptions import ValidationError


def assert_legacy_write_allowed(makerspace_id):
    from apps.machines.printing_cutover import kernel_is_authoritative
    from apps.makerspaces.models import Makerspace

    if makerspace_id and kernel_is_authoritative(Makerspace.objects.get(pk=makerspace_id)):
        raise ValidationError("Legacy printing is read-only after the machine-kernel cutover.")
