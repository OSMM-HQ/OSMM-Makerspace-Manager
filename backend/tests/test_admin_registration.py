from types import SimpleNamespace

from django.contrib import admin
from django.urls import NoReverseMatch

from config.unfold import UNFOLD


def test_unfold_sidebar_links_all_resolve():
    """Every curated Unfold sidebar link must point at a registered admin route,
    or the whole admin sidebar breaks with NoReverseMatch at render."""
    broken = []
    for group in UNFOLD["SIDEBAR"]["navigation"]:
        for item in group["items"]:
            try:
                str(item["link"])  # force the lazy reverse
            except NoReverseMatch:
                broken.append(str(item["title"]))
    assert broken == []

from apps.accounts.models import User
from apps.apiclients.models import ApiClient, ApiKeyRequest
from apps.audit.models import AuditLog
from apps.boxes.models import Box, BoxScan, QrCode, QrScanEvent
from apps.evidence.models import EvidencePhoto
from apps.hardware_requests.models import (
    HardwareRequest,
    HardwareRequestItemAsset,
    PublicToolLoan,
    RequesterAccountability,
    ReturnEvent,
)
from apps.integrations.models import EmailTemplate
from apps.inventory.models import Category, InventoryAsset, InventoryProduct
from apps.makerspaces.models import Makerspace, MakerspaceMembership
from apps.operations.models import (
    InventoryAdjustment,
    QrPrintBatch,
    StockTransfer,
    StocktakeSession,
)
from apps.printing.models import (
    FilamentSpool,
    ManualPrintLog,
    PrintBucket,
    PrintPrinter,
    PrintRequest,
)
from apps.procurement.models import ToBuyItem


def test_core_models_are_registered_in_django_admin():
    registered_models = {
        Makerspace,
        MakerspaceMembership,
        Category,
        InventoryProduct,
        InventoryAsset,
        Box,
        BoxScan,
        QrCode,
        QrScanEvent,
        HardwareRequest,
        EmailTemplate,
        PublicToolLoan,
        ReturnEvent,
        RequesterAccountability,
        HardwareRequestItemAsset,
        StockTransfer,
        StocktakeSession,
        InventoryAdjustment,
        QrPrintBatch,
        PrintBucket,
        PrintRequest,
        PrintPrinter,
        FilamentSpool,
        ManualPrintLog,
        ApiClient,
        ApiKeyRequest,
        AuditLog,
        EvidencePhoto,
        ToBuyItem,
        User,
    }

    assert registered_models <= set(admin.site._registry)


def test_immutable_admins_are_read_only():
    request = SimpleNamespace(user=SimpleNamespace(is_superuser=True))

    for model in (
        PublicToolLoan,
        ReturnEvent,
        RequesterAccountability,
        HardwareRequestItemAsset,
        BoxScan,
    ):
        model_admin = admin.site._registry[model]

        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_change_permission(request) is False
        assert model_admin.has_delete_permission(request) is False
