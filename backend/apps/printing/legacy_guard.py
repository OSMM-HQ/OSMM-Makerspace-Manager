"""Model-only compatibility fence for retained legacy table definitions."""

from django.core.exceptions import ValidationError


def assert_legacy_write_allowed(makerspace_id):
    """Block direct writes for cut-over tenants without restoring legacy services."""
    if not makerspace_id:
        return
    from apps.machines.models import PrintingCutoverState

    if PrintingCutoverState.objects.filter(
        makerspace_id=makerspace_id, kernel_authoritative_at__isnull=False,
    ).exists():
        raise ValidationError("Legacy printing is read-only after the machine-kernel cutover.")