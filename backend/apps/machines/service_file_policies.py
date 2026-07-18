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


def default_service_file_policy():
    return {"name": "documents", "version": 1}


def get_policy(name: str, version: int) -> ServiceFilePolicy:
    policy = _documents_policy()
    if (name, version) != (policy.name, policy.version):
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
