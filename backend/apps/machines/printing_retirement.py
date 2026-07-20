"""Read-only B7d preflight for retiring retained legacy printing tables."""

from django.apps import apps

from apps.machines.models import PrintingCutoverState
from apps.makerspaces.models import Makerspace


LEGACY_MODEL_NAMES = (
    "PrintBucket", "PrintPrinter", "FilamentSpool", "ManualPrintLog",
    "PrintRequest", "PrintRequestFile",
)


def legacy_printing_makerspace_ids():
    """Return tenants that still own legacy-print rows without importing its runtime."""
    models = {name: apps.get_model("printing", name) for name in LEGACY_MODEL_NAMES}
    ids = set()
    for name in ("PrintBucket", "PrintPrinter", "FilamentSpool", "ManualPrintLog", "PrintRequestFile"):
        ids.update(models[name].objects.values_list("makerspace_id", flat=True))
    ids.update(models["PrintRequest"].objects.values_list("bucket__makerspace_id", flat=True))
    return {maker_id for maker_id in ids if maker_id is not None}


def unready_makerspaces():
    enabled = set(Makerspace.objects.filter(enabled_modules__contains=["printing"]).values_list("pk", flat=True))
    candidates = enabled | legacy_printing_makerspace_ids()
    authoritative = set(PrintingCutoverState.objects.filter(
        makerspace_id__in=candidates, kernel_authoritative_at__isnull=False,
    ).values_list("makerspace_id", flat=True))
    return Makerspace.objects.filter(pk__in=candidates - authoritative).order_by("pk")