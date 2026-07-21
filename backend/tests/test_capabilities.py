import pytest
from django.core.exceptions import ValidationError

from apps.makerspaces.capabilities import default_enabled_features, validate_capabilities


def test_feature_registry_rejects_unknown_duplicate_and_missing_dependencies():
    with pytest.raises(ValidationError):
        validate_capabilities(["public_inventory"], ["inventory.unknown"])
    with pytest.raises(ValidationError):
        validate_capabilities(
            ["public_inventory"],
            ["inventory.self_checkout", "inventory.self_checkout"],
        )
    with pytest.raises(ValidationError):
        validate_capabilities(["machines"], ["payments.machines"])


def test_feature_defaults_are_dormant_except_legacy_compatible_self_checkout():
    assert default_enabled_features() == ["inventory.self_checkout"]
    assert not any(key.startswith("payments.") for key in default_enabled_features())


def test_self_checkout_is_standalone_and_independent_of_public_inventory():
    # Regression: self-checkout / direct handouts previously gated on the standalone
    # `self_checkout` module and NEVER required a public catalogue. A private makerspace
    # (no public_inventory) that enables the feature must keep it effective.
    from apps.makerspaces.models import Makerspace
    from apps.makerspaces.platform import feature_enabled

    private = Makerspace(
        name="Private", slug="private",
        enabled_modules=["staff_admin", "scanner"],
        enabled_features=["inventory.self_checkout"],
    )
    assert feature_enabled(private, "inventory.self_checkout") is True
    # And it validates with no parent module present.
    assert validate_capabilities([], ["inventory.self_checkout"]) == (
        [],
        ["inventory.self_checkout"],
    )


def test_machine_payment_requires_machines_and_machine_service():
    assert validate_capabilities(["machines", "machine_service"], ["payments.machines"]) == (
        ["machine_service", "machines"],
        ["payments.machines"],
    )


def test_effective_feature_requires_parent_and_typed_guard():
    from rest_framework.exceptions import ValidationError as DrfValidationError

    from apps.makerspaces.guards import require_feature
    from apps.makerspaces.models import Makerspace
    from apps.makerspaces.platform import feature_enabled

    makerspace = Makerspace(
        name="Dormant", slug="dormant", enabled_modules=["public_inventory"], enabled_features=[]
    )
    assert feature_enabled(makerspace, "inventory.self_checkout") is False
    with pytest.raises(DrfValidationError) as exc:
        require_feature(makerspace, "inventory.self_checkout")
    assert "feature" in exc.value.detail


def test_model_and_admin_validator_share_printing_rule():
    from apps.makerspaces.models import Makerspace

    makerspace = Makerspace(
        name="Print", slug="print", enabled_modules=["printing"], enabled_features=[]
    )
    with pytest.raises(ValidationError) as exc:
        makerspace.clean()
    assert "enabled_modules" in exc.value.message_dict
    with pytest.raises(ValidationError):
        validate_capabilities(["printing"], [])


def test_feature_dependency_and_bootstrap_projection():
    from apps.makerspaces.models import Makerspace
    from apps.makerspaces.platform import bootstrap_payload, feature_enabled

    makerspace = Makerspace(
        id=7,
        name="Machines",
        slug="machines",
        public_code="ABCD",
        public_api_key="pk_test",
        enabled_modules=["machines", "machine_service"],
        enabled_features=["payments.machines"],
    )
    assert feature_enabled(makerspace, "payments.machines") is True
    payload = bootstrap_payload(makerspace)
    assert payload["features"] == ["payments.machines"]
    assert "telegram_bot_token" not in payload

def test_staff_serializer_splits_module_and_feature_capability_writes():
    from rest_framework.exceptions import PermissionDenied
    from rest_framework.exceptions import ValidationError as DrfValidationError
    from rest_framework.test import APIRequestFactory

    from apps.admin_api.serializers_makerspaces import MakerspaceSerializer
    from apps.makerspaces.models import Makerspace

    request = APIRequestFactory().patch("/makerspaces/1", {})
    module_serializer = MakerspaceSerializer(
        Makerspace(name="Modules", slug="modules"),
        data={"enabled_modules": ["public_inventory"]},
        partial=True,
        context={"request": request},
    )
    with pytest.raises(PermissionDenied):
        module_serializer.is_valid(raise_exception=True)

    enabled_feature_serializer = MakerspaceSerializer(
        Makerspace(
            name="Feature enabled",
            slug="feature-enabled",
            enabled_modules=["public_inventory"],
            enabled_features=[],
        ),
        data={"enabled_features": ["inventory.self_checkout"]},
        partial=True,
        context={"request": request},
    )
    assert enabled_feature_serializer.is_valid(raise_exception=True) is True
    assert enabled_feature_serializer.validated_data["enabled_features"] == [
        "inventory.self_checkout"
    ]

    disabled_feature_serializer = MakerspaceSerializer(
        Makerspace(
            name="Feature disabled",
            slug="feature-disabled",
            enabled_modules=["public_inventory"],
            enabled_features=[],
        ),
        data={"enabled_features": ["payments.machines"]},
        partial=True,
        context={"request": request},
    )
    with pytest.raises(DrfValidationError):
        disabled_feature_serializer.is_valid(raise_exception=True)


def test_admin_form_rejects_child_without_parent_even_when_ui_is_bypassed():
    from apps.makerspaces.admin_capabilities import MakerspaceAdminForm
    from apps.makerspaces.models import Makerspace

    form = MakerspaceAdminForm(instance=Makerspace(name="Admin", slug="admin"))
    form.cleaned_data = {"capabilities": ["feature:payments.machines"]}
    with pytest.raises(Exception):
        form.clean_capabilities()

def test_admin_form_allows_standalone_self_checkout_without_public_inventory():
    # The /control/ matrix must persist a parentless feature even when no public
    # catalogue module is enabled (P2 silent-clear guard).
    from apps.makerspaces.admin_capabilities import MakerspaceAdminForm
    from apps.makerspaces.models import Makerspace

    instance = Makerspace(name="Private admin", slug="private-admin")
    form = MakerspaceAdminForm(instance=instance)
    form.cleaned_data = {
        "capabilities": ["module:staff_admin", "feature:inventory.self_checkout"]
    }
    form.clean_capabilities()
    assert "inventory.self_checkout" in instance.enabled_features
    assert "public_inventory" not in instance.enabled_modules


def test_membership_payment_cannot_be_effective_before_membership_module_exists():
    from apps.makerspaces.models import Makerspace
    from apps.makerspaces.platform import feature_enabled

    makerspace = Makerspace(
        name="No membership", slug="no-membership", enabled_modules=["membership"],
        enabled_features=["payments.membership"],
    )
    assert feature_enabled(makerspace, "payments.membership") is False
    with pytest.raises(ValidationError):
        validate_capabilities(["membership"], ["payments.membership"])