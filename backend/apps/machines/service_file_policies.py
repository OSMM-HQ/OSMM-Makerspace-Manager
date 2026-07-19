"""Built-in, versioned attachment policies for machine service requests."""

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class ServiceFilePolicy:
    name: str
    version: int
    allowed_extensions: tuple[str, ...]
    allowed_mimes: tuple[str, ...]
    max_bytes: int


def _documents_policy():
    return ServiceFilePolicy(
        name="documents",
        version=1,
        allowed_extensions=tuple(settings.MACHINE_DOC_ALLOWED_EXT),
        allowed_mimes=tuple(settings.MACHINE_DOC_ALLOWED_MIME),
        max_bytes=settings.MACHINE_DOC_MAX_BYTES,
    )


def _printer_policy():
    return ServiceFilePolicy(
        name="printer", version=1,
        allowed_extensions=("stl", "3mf", "step", "stp", "obj", "pdf", "png", "jpg", "jpeg", "webp"),
        allowed_mimes=(
            "model/stl", "application/sla", "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
            "model/step", "application/step", "model/obj", "application/pdf", "image/png", "image/jpeg", "image/webp",
        ),
        max_bytes=settings.MACHINE_DOC_MAX_BYTES,
    )


def default_service_file_policy():
    return {"name": "documents", "version": 1}


def get_policy(name: str, version: int) -> ServiceFilePolicy:
    policies = {_documents_policy().name: _documents_policy(), _printer_policy().name: _printer_policy()}
    policy = policies.get(name)
    if policy is None or version != policy.version:
        raise ValidationError("Unknown machine service file policy.")
    return policy


def validate_service_file_policy(value):
    if not isinstance(value, dict) or set(value) != {"name", "version"}:
        raise ValidationError("File policy must contain only name and version.")
    name, version = value.get("name"), value.get("version")
    if not isinstance(name, str) or not isinstance(version, int) or isinstance(version, bool):
        raise ValidationError("File policy name and version are invalid.")
    get_policy(name, version)


def policy_for_machine(machine) -> ServiceFilePolicy:
    value = machine.service_file_policy
    validate_service_file_policy(value)
    return get_policy(value["name"], value["version"])


def policy_for_queue(queue) -> ServiceFilePolicy:
    value = queue.machine_type.capability_config or {}
    policy = value.get("service_file_policy") or default_service_file_policy()
    validate_service_file_policy(policy)
    return get_policy(policy["name"], policy["version"])
