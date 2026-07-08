import dns.resolver
from django.utils import timezone

from apps.makerspaces.models import Makerspace

EXPECTED_HOST_PREFIX = "_osmm-verify"


def expected_record(makerspace):
    if not makerspace.frontend_domain:
        return None
    return {
        "host": f"{EXPECTED_HOST_PREFIX}.{makerspace.frontend_domain}",
        "type": "TXT",
        "value": makerspace.domain_verification_token,
    }


def _resolve_txt(name):
    resolver = dns.resolver.Resolver()
    resolver.timeout = 5
    resolver.lifetime = 5
    answers = resolver.resolve(name, "TXT")
    return [
        b"".join(part for part in answer.strings).decode("utf-8")
        for answer in answers
    ]


def verify_domain(makerspace):
    if not makerspace.frontend_domain:
        makerspace.frontend_domain_status = Makerspace.DomainStatus.PENDING
        makerspace.domain_verified_at = None
        makerspace.save(
            update_fields=[
                "frontend_domain_status",
                "domain_verified_at",
                "updated_at",
            ]
        )
        return (Makerspace.DomainStatus.PENDING, None, "No custom domain set.")

    name = f"{EXPECTED_HOST_PREFIX}.{makerspace.frontend_domain}"
    try:
        records = _resolve_txt(name)
    except Exception as exc:  # DNS failures are verification state, not request failures.
        makerspace.frontend_domain_status = Makerspace.DomainStatus.FAILED
        makerspace.save(update_fields=["frontend_domain_status", "updated_at"])
        return (
            Makerspace.DomainStatus.FAILED,
            makerspace.domain_verified_at,
            f"DNS lookup failed: {exc}",
        )

    if makerspace.domain_verification_token in records:
        verified_at = timezone.now()
        makerspace.frontend_domain_status = Makerspace.DomainStatus.VERIFIED
        makerspace.domain_verified_at = verified_at
        makerspace.save(
            update_fields=[
                "frontend_domain_status",
                "domain_verified_at",
                "updated_at",
            ]
        )
        return (Makerspace.DomainStatus.VERIFIED, verified_at, "Domain verified.")

    makerspace.frontend_domain_status = Makerspace.DomainStatus.FAILED
    makerspace.save(update_fields=["frontend_domain_status", "updated_at"])
    return (
        Makerspace.DomainStatus.FAILED,
        makerspace.domain_verified_at,
        "Verification token was not found in DNS TXT records.",
    )