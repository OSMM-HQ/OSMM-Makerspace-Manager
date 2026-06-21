from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.template.response import TemplateResponse
from unfold.admin import ModelAdmin, TabularInline

from apps.hardware_requests import admin_loans  # noqa: F401
from apps.hardware_requests import admin_requests  # noqa: F401
from apps.hardware_requests.admin_loans import (
    HardwareRequestItemAssetAdmin,
    PublicToolLoanAdmin,
    RequesterAccountabilityAdmin,
    ReturnEventAdmin,
)
from apps.hardware_requests.admin_requests import (
    HardwareRequestAdmin,
    HardwareRequestItemInline,
)
from apps.hardware_requests.admin_workflow import WORKFLOW_EXCEPTIONS
from apps.hardware_requests.asset_link_models import HardwareRequestItemAsset
from apps.hardware_requests.handover_workflow import assign_box
from apps.hardware_requests.models import (
    HardwareRequest,
    HardwareRequestItem,
)
from apps.hardware_requests.request_workflow import accept_request, reject_request
from apps.hardware_requests.return_models import RequesterAccountability, ReturnEvent
from apps.hardware_requests.self_checkout_models import PublicToolLoan
from apps.hardware_requests.workflow_errors import (
    BoxUnavailable,
    BoxValidationError,
    InvalidTransition,
    RequestValidationError,
    RequesterBlocked,
)
from apps.inventory.availability import InsufficientStock
from config.admin_access import SuperuserOnlyModelAdmin

__all__ = [
    "ACTION_CHECKBOX_NAME",
    "BoxUnavailable",
    "BoxValidationError",
    "HardwareRequest",
    "HardwareRequestAdmin",
    "HardwareRequestItem",
    "HardwareRequestItemAsset",
    "HardwareRequestItemAssetAdmin",
    "HardwareRequestItemInline",
    "InsufficientStock",
    "InvalidTransition",
    "ModelAdmin",
    "PublicToolLoan",
    "PublicToolLoanAdmin",
    "RequesterAccountability",
    "RequesterAccountabilityAdmin",
    "RequestValidationError",
    "RequesterBlocked",
    "ReturnEvent",
    "ReturnEventAdmin",
    "SuperuserOnlyModelAdmin",
    "TabularInline",
    "TemplateResponse",
    "WORKFLOW_EXCEPTIONS",
    "accept_request",
    "admin",
    "assign_box",
    "messages",
    "reject_request",
]
