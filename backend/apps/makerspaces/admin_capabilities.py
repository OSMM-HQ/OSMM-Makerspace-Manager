"""Superadmin-only structured capability controls for Makerspace admin."""

from django import forms

from apps.audit import services as audit
from apps.makerspaces.capabilities import FEATURE_DEFINITIONS, validate_capabilities
from apps.makerspaces.admin_images import MakerspaceAdminForm as ImageMakerspaceAdminForm
from apps.makerspaces.models import DEFAULT_ENABLED_MODULES


class CapabilityMatrixWidget(forms.CheckboxSelectMultiple):
    template_name = "admin/makerspaces/capability_matrix.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        # Authoritative parent map (feature option value -> parent module or None) so the
        # client derives the disable rule from the real definition instead of guessing from
        # the key. Parentless features (parent is None) must never be disabled: a disabled
        # checkbox is omitted from POST, which would silently clear the capability on save.
        context["feature_parents"] = {
            f"feature:{item.key}": item.parent_module for item in FEATURE_DEFINITIONS
        }
        return context


def _feature_label(feature):
    requirements = [
        requirement
        for requirement in (feature.parent_module, *feature.requires_modules, *feature.requires_features)
        if requirement
    ]
    if not requirements:
        return f"-> {feature.label}"
    return f"-> {feature.label} (requires {', '.join(requirements)})"

class MakerspaceAdminForm(ImageMakerspaceAdminForm):
    capabilities = forms.MultipleChoiceField(
        required=False,
        label="Modules and features",
        widget=CapabilityMatrixWidget,
    )

    class Meta(ImageMakerspaceAdminForm.Meta):
        exclude = ("enabled_modules", "enabled_features")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        modules = list(DEFAULT_ENABLED_MODULES)
        modules.extend(
            key for key in (self.instance.enabled_modules or []) if key not in modules
        )
        choices = [(f"module:{key}", key.replace("_", " ").title()) for key in modules]
        choices.extend(
            (f"feature:{item.key}", _feature_label(item))
            for item in FEATURE_DEFINITIONS
        )
        self.fields["capabilities"].choices = choices
        selected = [f"module:{key}" for key in self.instance.enabled_modules or []]
        selected.extend(f"feature:{key}" for key in self.instance.enabled_features or [])
        self.initial["capabilities"] = selected
        self.capability_before = {
            "modules": sorted(set(self.instance.enabled_modules or [])),
            "features": sorted(set(self.instance.enabled_features or [])),
        }

    def clean_capabilities(self):
        values = self.cleaned_data["capabilities"]
        modules = [value.removeprefix("module:") for value in values if value.startswith("module:")]
        features = [value.removeprefix("feature:") for value in values if value.startswith("feature:")]
        try:
            modules, features = validate_capabilities(modules, features)
        except Exception as exc:
            raise forms.ValidationError(exc.messages) from exc
        self.instance.enabled_modules = modules
        self.instance.enabled_features = features
        return values


class MakerspaceCapabilityAdminMixin:
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        before = getattr(form, "capability_before", {"modules": [], "features": []})
        after = {
            "modules": sorted(set(obj.enabled_modules or [])),
            "features": sorted(set(obj.enabled_features or [])),
        }
        if change and before != after:
            audit.record(
                request.user,
                "makerspace.capabilities_changed",
                makerspace=obj,
                target=obj,
                meta={"before": before, "after": after},
            )