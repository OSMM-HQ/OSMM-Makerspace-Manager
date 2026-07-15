"""Auto-link every newly created PrintPrinter to a generalized Machine record.

Fires on PrintPrinter creation from ANY path (API, Django admin, seed) via a
transaction.on_commit hook, so the link is created once the printer row is durable.
link_printer is fail-safe (never raises), so printer creation can never break.
"""
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.machines.linking import link_printer
from apps.printing.models import PrintPrinter


@receiver(post_save, sender=PrintPrinter, dispatch_uid="machines_link_printer")
def link_printer_on_create(sender, instance, created, **kwargs):
    if not created:
        return
    transaction.on_commit(lambda: link_printer(instance))
