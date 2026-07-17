import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit import services as audit

logger = logging.getLogger(__name__)

def archive(makerspace, actor):
    with transaction.atomic():
        locked = makerspace.__class__.objects.select_for_update().get(pk=makerspace.pk)
        if not locked.superadmin_access_enabled:
            raise ValidationError("Cannot archive a hidden makerspace.")
        if locked.archived_at is not None:
            raise ValidationError("Makerspace is already archived.")

        locked.archived_at = timezone.now()
        locked.archived_by = actor
        locked.public_inventory_enabled = False
        locked.save(update_fields=["archived_at", "archived_by", "public_inventory_enabled"])
        audit.record(actor, "makerspace.archived", makerspace=locked, target=locked)
        return locked


def unarchive(makerspace, actor):
    with transaction.atomic():
        locked = makerspace.__class__.objects.select_for_update().get(pk=makerspace.pk)
        if not locked.superadmin_access_enabled:
            raise ValidationError("Cannot unarchive a hidden makerspace.")
        if locked.archived_at is None:
            raise ValidationError("Makerspace is not archived.")

        locked.archived_at = None
        locked.archived_by = None
        locked.save(update_fields=["archived_at", "archived_by"])
        audit.record(actor, "makerspace.unarchived", makerspace=locked, target=locked)
        return locked


def purge(makerspace, actor):
    if makerspace.archived_at is None:
        raise ValidationError("Cannot purge a makerspace that is not archived.")
    if not makerspace.superadmin_access_enabled:
        raise ValidationError("Cannot purge a hidden makerspace.")
    if not getattr(actor, "is_superuser", False):
        raise ValidationError("Only a superuser can purge a makerspace.")

    storage_keys = _collect_storage_keys(makerspace)
    public_image_keys = _collect_public_image_keys(makerspace)
    meta = _audit_meta(makerspace)

    audit.record(actor, "makerspace.purge_started", makerspace=None, target=None, meta=meta)

    with transaction.atomic():
        locked = makerspace.__class__.objects.select_for_update().get(pk=makerspace.pk)
        if locked.archived_at is None:
            raise ValidationError("Cannot purge a makerspace that is not archived.")
        if not locked.superadmin_access_enabled:
            raise ValidationError("Cannot purge a hidden makerspace.")
        _delete_object_graph(locked)

    audit.record(actor, "makerspace.purged", makerspace=None, target=None, meta=meta)
    _delete_storage_keys(storage_keys)
    _delete_public_image_keys(public_image_keys)


def _audit_meta(makerspace):
    return {
        "makerspace_id": makerspace.pk,
        "name": makerspace.name,
        "slug": makerspace.slug,
    }


def _collect_storage_keys(makerspace):
    from apps.evidence.models import EvidencePhoto
    from apps.printing.models import PrintRequest, PrintRequestFile
    from apps.procurement.models import ToBuyReceipt
    from apps.warranty.models import WarrantyDocument
    from apps.maintenance.models import MaintenanceLogDocument
    from apps.machines.models import MachineDocument
    from apps.machines.service_lifecycle import collect_private_object_keys

    keys = []
    seen = set()

    def add(key):
        if key and key not in seen:
            seen.add(key)
            keys.append(key)

    for key in EvidencePhoto.objects.filter(makerspace=makerspace).values_list("object_key", flat=True):
        add(key)

    for key in PrintRequestFile.objects.filter(makerspace=makerspace).values_list("object_key", flat=True):
        add(key)

    for key in WarrantyDocument.objects.filter(
        warranty__makerspace=makerspace
    ).values_list("object_key", flat=True):
        add(key)

    for key in ToBuyReceipt.objects.filter(
        to_buy_item__makerspace=makerspace
    ).values_list("object_key", flat=True):
        add(key)

    for key in MaintenanceLogDocument.objects.filter(
        log__machine__makerspace=makerspace
    ).values_list("object_key", flat=True):
        add(key)

    for key in MachineDocument.objects.filter(
        machine__makerspace=makerspace
    ).values_list("object_key", flat=True):
        add(key)

    collect_private_object_keys(makerspace, add)

    for request in PrintRequest.objects.filter(bucket__makerspace=makerspace).only(
        "model_file", "estimate_screenshot", "preview_screenshot"
    ):
        add(request.model_file.name)
        add(request.estimate_screenshot.name)
        add(request.preview_screenshot.name)

    return keys


def _collect_public_image_keys(makerspace):
    from apps.bookings.models import BookableSpace
    from apps.inventory.models import InventoryProduct
    from apps.machines.models import Machine
    from apps.printing.models import PrintPrinter

    keys = []
    seen = set()

    def add(key):
        if key and key not in seen:
            seen.add(key)
            keys.append(key)

    add(makerspace.logo_key)
    add(makerspace.cover_image_key)
    for key in BookableSpace.objects.filter(makerspace=makerspace).values_list(
        'image_key',
        flat=True,
    ):
        add(key)

    for key in InventoryProduct.objects.filter(makerspace=makerspace).values_list(
        "image_key",
        flat=True,
    ):
        add(key)
    for key in PrintPrinter.objects.filter(makerspace=makerspace).values_list(
        "image_key",
        flat=True,
    ):
        add(key)
    for key in Machine.objects.filter(makerspace=makerspace).values_list(
        "image_key",
        flat=True,
    ):
        add(key)

    return keys


def _delete_object_graph(makerspace):
    from apps.apiclients.models import ApiClient, ApiKeyRequest
    from apps.audit.models import AuditLog
    from apps.boxes.models import Box, BoxScan, QrCode, QrScanEvent
    from apps.evidence.models import EvidencePhoto
    from apps.hardware_requests.models import HardwareRequest
    from apps.hardware_requests.models import PublicToolLoan, RequesterAccountability
    from apps.hardware_requests.models import ReturnEvent
    from apps.hardware_requests.asset_link_models import HardwareRequestItemAsset
    from apps.integrations.models import EmailTemplate
    from apps.inventory.models import Category, InventoryAsset, InventoryProduct
    from apps.makerspaces.models import MakerspaceMembership
    from apps.operations.models import InventoryAdjustment, QrPrintBatch
    from apps.operations.models import StocktakeSession, StockTransfer
    from apps.printing.models import FilamentSpool, ManualPrintLog, PrintBucket
    from apps.printing.models import PrintPrinter, PrintRequest, PrintRequestFile
    from apps.machines.models import Machine, MachineType
    from apps.machines.service_lifecycle import delete_for_makerspace

    with connection.cursor() as cursor:
        # Suspend ALL triggers for THIS transaction only via the session-replication
        # role. It is transaction-scoped — Postgres resets it on commit/rollback, and a
        # dropped connection resets it too — so a crash mid-purge can NEVER leave the
        # append-only immutability triggers durably disabled platform-wide. (ALTER TABLE
        # DISABLE TRIGGER cannot be re-enabled inside the same transaction that modified
        # the table — "pending trigger events" — forcing a post-commit re-enable that is
        # not crash-safe.) Django's ORM performs every CASCADE/SET_NULL fixup in Python
        # and the comprehensive purge test asserts no orphans survive, so losing DB-level
        # FK enforcement for this one transaction is safe.
        if settings.MANAGED_POSTGRES:
            # Managed Postgres (e.g. Supabase) forbids session_replication_role (needs
            # superuser). Use a custom transaction-scoped GUC that our immutability
            # triggers honor to allow DELETE only; FK triggers stay ON (Django collects
            # the graph in dependency order). Auto-resets on commit/rollback.
            cursor.execute("SET LOCAL app.allow_immutable_delete = 'on'")
        else:
            cursor.execute("SET LOCAL session_replication_role = 'replica'")

        QrPrintBatch.objects.filter(makerspace=makerspace).delete()
        StockTransfer.objects.filter(
            Q(makerspace=makerspace)
            | Q(source_makerspace=makerspace)
            | Q(destination_makerspace=makerspace)
            | Q(source_container__makerspace=makerspace)
            | Q(destination_container__makerspace=makerspace)
            | Q(lines__product__makerspace=makerspace)
            | Q(lines__asset__makerspace=makerspace)
        ).distinct().delete()
        StocktakeSession.objects.filter(makerspace=makerspace).delete()
        InventoryAdjustment.objects.filter(makerspace=makerspace).delete()

        ManualPrintLog.objects.filter(makerspace=makerspace).delete()
        PrintRequestFile.objects.filter(makerspace=makerspace).delete()
        PrintRequest.objects.filter(bucket__makerspace=makerspace).delete()
        PrintBucket.objects.filter(makerspace=makerspace).delete()
        FilamentSpool.objects.filter(makerspace=makerspace).delete()
        PrintPrinter.objects.filter(makerspace=makerspace).delete()

        delete_for_makerspace(makerspace, cursor)

        HardwareRequestItemAsset.objects.filter(request_item__request__makerspace=makerspace).delete()
        BoxScan.objects.filter(makerspace=makerspace).delete()
        QrScanEvent.objects.filter(makerspace=makerspace).delete()
        PublicToolLoan.objects.filter(makerspace=makerspace).delete()
        RequesterAccountability.objects.filter(makerspace=makerspace).delete()
        ReturnEvent.objects.filter(makerspace=makerspace).delete()
        HardwareRequest.objects.filter(makerspace=makerspace).delete()
        EvidencePhoto.objects.filter(makerspace=makerspace).delete()
        QrCode.objects.filter(makerspace=makerspace).delete()

        # Machines + their maintenance/children/consumables cascade from the Machine
        # delete (triggers suspended above). Do this BEFORE InventoryProduct because
        # MachineConsumable.product is PROTECT; and clear the makerspace-scoped custom
        # MachineType (PROTECT makerspace FK) before makerspace.delete().
        Machine.objects.filter(makerspace=makerspace).delete()
        MachineType.objects.filter(makerspace=makerspace).delete()

        InventoryAsset.objects.filter(makerspace=makerspace).delete()
        InventoryProduct.objects.filter(makerspace=makerspace).delete()
        Category.objects.filter(makerspace=makerspace).delete()
        Box.objects.filter(makerspace=makerspace).delete()

        EmailTemplate.objects.filter(makerspace=makerspace).delete()
        ApiClient.objects.filter(makerspace=makerspace).delete()
        ApiKeyRequest.objects.filter(makerspace=makerspace).delete()
        MakerspaceMembership.objects.filter(makerspace=makerspace).delete()
        AuditLog.objects.filter(makerspace=makerspace).delete()
        # Encryption key rows carry a PROTECT FK + a no-delete ORM guard/trigger, so
        # raw-delete them inside this authorized purge context (session_replication_role
        # =replica self-host, or app.allow_immutable_delete GUC managed) before the
        # parent delete; otherwise the PROTECT FK would block teardown once a makerspace
        # has ever had scoped-PII encryption enabled.
        cursor.execute(
            "DELETE FROM encryption_makerspaceencryptionkey WHERE makerspace_id = %s",
            [makerspace.id],
        )
        makerspace.delete()


def _delete_storage_keys(storage_keys):
    if not storage_keys:
        return

    from apps.evidence import storage

    try:
        client = storage._client()
    except Exception:
        logger.exception("Failed to create storage client for makerspace purge keys: %s", storage_keys)
        return

    for key in storage_keys:
        try:
            client.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)
        except Exception:
            logger.exception("Failed to delete makerspace purge storage key: %s", key)


def _delete_public_image_keys(storage_keys):
    if not storage_keys:
        return

    from apps.inventory import public_image_storage

    for key in storage_keys:
        public_image_storage.delete_object(key)
