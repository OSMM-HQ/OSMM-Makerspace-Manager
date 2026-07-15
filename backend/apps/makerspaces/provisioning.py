import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.makerspaces.hosting import canonical_host
from apps.makerspaces.models import Makerspace


RESERVED_LABELS: frozenset[str] = frozenset(
    {
        "www",
        "api",
        "app",
        "admin",
        "control",
        "static",
        "files",
        "origin",
        "mail",
        "cdn",
        "assets",
        "status",
        "help",
        "docs",
        "blog",
        "portal",
        "dashboard",
    }
)
LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def provision_subdomain(makerspace, label: str, actor) -> Makerspace:
    suffix = str(settings.PLATFORM_DOMAIN_SUFFIX or "").strip().lower()
    if not suffix:
        raise ValidationError("Platform subdomains are not enabled.")

    normalized_label = str(label or "").strip().lower()
    if "." in normalized_label or not LABEL_RE.fullmatch(normalized_label):
        raise ValidationError("Enter a valid single subdomain label.")
    if normalized_label in RESERVED_LABELS:
        raise ValidationError("This subdomain label is reserved.")

    domain = f"{normalized_label}{suffix}"
    canonical = canonical_host(domain)
    if (
        not suffix.startswith(".")
        or canonical != domain
        or canonical[: -len(suffix)] != normalized_label
    ):
        raise ValidationError("The platform domain suffix is invalid.")

    try:
        with transaction.atomic():
            locked = Makerspace.objects.select_for_update().get(pk=makerspace.pk)
            locked.frontend_domain = domain
            locked.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
            locked.domain_verified_at = timezone.now()
            locked.save(
                update_fields=[
                    "frontend_domain",
                    "frontend_domain_status",
                    "domain_verified_at",
                    "updated_at",
                ]
            )
            audit.record(
                actor,
                "makerspace.subdomain_provisioned",
                makerspace=locked,
                target=locked,
                meta={"frontend_domain": domain},
            )
            return locked
    except IntegrityError as exc:
        raise ValidationError("This platform subdomain is already in use.") from exc
