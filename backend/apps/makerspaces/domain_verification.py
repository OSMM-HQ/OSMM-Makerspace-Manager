import dns.resolver
from django.conf import settings
from django.utils import timezone

from apps.makerspaces.hosting import canonical_host
from apps.makerspaces.models import Makerspace

EXPECTED_HOST_PREFIX = "_osmm-verify"
DOMAIN_CHANGE_COOLDOWN_MESSAGE = (
    "You changed your domain recently; please wait before changing it again."
)


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


def resolves_to_origin(makerspace) -> bool:
    configured_origin = str(settings.PLATFORM_ORIGIN_HOST or "").strip()
    if not configured_origin:
        return True

    domain = canonical_host(makerspace.frontend_domain or "")
    origin = canonical_host(configured_origin)
    if domain is None or origin is None:
        return False

    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = 5
        resolver.lifetime = 5
        try:
            cname_answers = resolver.resolve(domain, "CNAME")
        except dns.resolver.NoAnswer:
            cname_answers = ()
        if any(
            canonical_host(str(answer.target)) == origin
            for answer in cname_answers
        ):
            return True

        domain_addresses = {str(answer) for answer in resolver.resolve(domain, "A")}
        origin_addresses = {str(answer) for answer in resolver.resolve(origin, "A")}
        return bool(domain_addresses & origin_addresses)
    except Exception:
        return False


def domain_change_cooldown_active(makerspace, normalized_domain) -> bool:
    cooldown_seconds = settings.DOMAIN_CHANGE_COOLDOWN_SECONDS
    return bool(
        cooldown_seconds > 0
        and makerspace is not None
        and normalized_domain != makerspace.frontend_domain
        and makerspace.frontend_domain_changed_at is not None
        and (timezone.now() - makerspace.frontend_domain_changed_at).total_seconds()
        < cooldown_seconds
    )


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
        if not resolves_to_origin(makerspace):
            makerspace.frontend_domain_status = Makerspace.DomainStatus.FAILED
            makerspace.save(update_fields=["frontend_domain_status", "updated_at"])
            return (
                Makerspace.DomainStatus.FAILED,
                makerspace.domain_verified_at,
                "Domain does not resolve to the platform origin yet.",
            )
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
