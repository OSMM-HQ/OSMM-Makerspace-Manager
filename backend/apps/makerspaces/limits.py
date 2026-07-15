"""Managed-platform fair-use limits; deliberately dormant on self-hosts."""

from collections.abc import Callable
from datetime import UTC, datetime

from django.conf import settings
from rest_framework import serializers

from apps.makerspaces.domain_verification import is_self_host

NUMERIC_LIMIT_KEYS = frozenset(
    {
        "products",
        "assets",
        "machines",
        "events",
        "staff",
        "storage",
        "print",
        "email",
        "api_clients",
    }
)
BOOLEAN_LIMIT_KEYS = frozenset({"custom_domain"})
KNOWN_LIMIT_KEYS = NUMERIC_LIMIT_KEYS | BOOLEAN_LIMIT_KEYS

RESOURCE_LABELS = {
    "products": "products",
    "assets": "assets",
    "machines": "machines",
    "events": "events",
    "staff": "staff members",
    "storage": "storage",
    "print": "monthly print requests",
    "email": "daily emails",
    "api_clients": "API clients",
    "custom_domain": "custom domains",
}


def resource_limit(makerspace, key) -> int | None:
    """Return the effective managed limit; ``None`` means unlimited."""
    if is_self_host():
        return None
    overrides = makerspace.resource_limit_overrides or {}
    if key in overrides:
        value = overrides[key]
        if value is None or value == -1:
            return None
        return int(value)
    return settings.MANAGED_RESOURCE_LIMITS.get(key)


def custom_domain_allowed(makerspace) -> bool:
    if is_self_host():
        return True
    return bool((makerspace.resource_limit_overrides or {}).get("custom_domain"))


def _products(makerspace) -> int:
    from apps.inventory.models import InventoryProduct

    return InventoryProduct.objects.filter(
        makerspace=makerspace, is_archived=False
    ).count()


def _assets(makerspace) -> int:
    from apps.inventory.models import InventoryAsset

    return InventoryAsset.objects.filter(
        makerspace=makerspace, product__is_archived=False
    ).count()


def _machines(makerspace) -> int:
    from apps.machines.models import Machine

    return Machine.objects.filter(makerspace=makerspace, is_active=True).count()


def _staff(makerspace) -> int:
    from apps.accounts.models import User
    from apps.makerspaces.models import MakerspaceMembership

    return MakerspaceMembership.objects.filter(
        makerspace=makerspace,
        user__is_active=True,
        user__access_status=User.AccessStatus.ACTIVE,
    ).count()


def _api_clients(makerspace) -> int:
    from apps.apiclients.models import ApiClient

    return ApiClient.objects.filter(makerspace=makerspace, is_active=True).count()


def _print_requests(makerspace) -> int:
    from apps.printing.models import PrintRequest

    now = datetime.now(UTC)
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    return PrintRequest.objects.filter(
        bucket__makerspace=makerspace,
        created_at__gte=month_start,
        created_at__lt=next_month,
    ).count()


def _storage(makerspace) -> int:
    return makerspace.storage_bytes_used


_COUNTERS: dict[str, Callable[[object], int]] = {
    "products": _products,
    "assets": _assets,
    "machines": _machines,
    "staff": _staff,
    "api_clients": _api_clients,
    "print": _print_requests,
    "storage": _storage,
}


def check_quota(makerspace, key, *, adding=1) -> None:
    """Raise when a managed limit would be exceeded.

    The caller must wrap this check and its create operation in
    ``transaction.atomic()`` so the makerspace row lock serializes creators.
    """
    limit = resource_limit(makerspace, key)
    if limit is None:
        return

    counter = _COUNTERS.get(key)
    if counter is None:
        raise NotImplementedError(f"No quota counter is registered for {key!r}.")

    from apps.makerspaces.models import Makerspace

    locked = Makerspace.objects.select_for_update().get(pk=makerspace.pk)
    current = counter(locked)
    if current + adding > limit:
        resource = RESOURCE_LABELS.get(key, key.replace("_", " "))
        message = (
            f"You've reached the free {resource} limit for this space — "
            "ask the operator to raise it or self-host."
        )
        raise serializers.ValidationError(
            {"limit": message}, code="limit_reached"
        )


def validate_resource_limit_overrides(value) -> dict:
    if not isinstance(value, dict):
        raise serializers.ValidationError("Resource limit overrides must be an object.")

    validated = {}
    for key, limit in value.items():
        if key not in KNOWN_LIMIT_KEYS:
            raise serializers.ValidationError(f"Unknown resource limit key: {key}.")
        if key in BOOLEAN_LIMIT_KEYS:
            if not isinstance(limit, bool):
                raise serializers.ValidationError(
                    {key: "This resource limit must be true or false."}
                )
        elif limit is not None and (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < -1
        ):
            raise serializers.ValidationError(
                {key: "Use a non-negative integer, -1, or null."}
            )
        validated[key] = limit
    return validated
