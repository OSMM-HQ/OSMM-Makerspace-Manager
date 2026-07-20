"""Fail-safe linkage between printing printers and generalized machines."""
import logging

from apps.machines.models import Machine, MachineType
from apps.printing.models import PrintPrinter

logger = logging.getLogger(__name__)


def _status_for(printer):
    if not printer.is_active or printer.status == PrintPrinter.Status.OFFLINE:
        return Machine.Status.OFFLINE
    if printer.status == PrintPrinter.Status.MAINTENANCE:
        return Machine.Status.MAINTENANCE
    return Machine.Status.IDLE


def link_printer(printer):
    try:
        machine_type = MachineType.objects.get(
            makerspace__isnull=True,
            slug="3d_printer",
        )
        if printer.makerspace_id is None:
            return None
        machine, _ = Machine.objects.get_or_create(
            linked_print_printer=printer,
            defaults={
                "makerspace_id": printer.makerspace_id,
                "machine_type": machine_type,
                "name": getattr(printer, "name", None) or f"Printer {printer.pk}",
                "type_payload": {"model": getattr(printer, "model", "") or "Legacy printer"},
                "status": _status_for(printer),
                "is_active": True,
            },
        )
        return machine
    except Exception:
        logger.exception(
            "Failed to link print printer %s to a machine.",
            getattr(printer, "pk", None),
        )
        return None


def reconcile_all():
    linked = 0
    for printer in PrintPrinter.objects.filter(machine__isnull=True):
        if link_printer(printer) is not None:
            linked += 1
    return linked
