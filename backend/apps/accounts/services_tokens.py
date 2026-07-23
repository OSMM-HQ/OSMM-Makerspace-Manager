def blacklist_outstanding_tokens(user):
    # Invalidate every refresh token issued before a password rotation so old
    # sessions cannot persist after the credential changes.
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)

    # Password changes/resets are global credential invalidation events. Native
    # access tokens are checked against their grant on every request, so revoke
    # those grants as well instead of waiting for their short JWT lifetime.
    from apps.accounts.models_devices import DeviceGrant

    for grant in DeviceGrant.objects.filter(
        user=user, status=DeviceGrant.Status.ACTIVE
    ):
        revoke_device_grant(grant)


def blacklist_device_family(family, *, revoke_grant=False, reuse=False):
    """Revoke a native refresh family and blacklist every persisted refresh JTI."""
    from django.utils import timezone
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    from apps.accounts.models_devices import DeviceGrant

    now = timezone.now()
    updates = {"revoked_at": now}
    if reuse:
        updates["reuse_detected_at"] = now
    type(family).objects.filter(pk=family.pk).update(**updates)
    family.revoked_at = now
    if reuse:
        family.reuse_detected_at = now
    jt_is = list(family.tokens.values_list("jti", flat=True))
    for token in OutstandingToken.objects.filter(jti__in=jt_is):
        BlacklistedToken.objects.get_or_create(token=token)
    family.tokens.filter(jti__in=jt_is).update(blacklisted_at=now)
    if revoke_grant:
        DeviceGrant.objects.filter(pk=family.grant_id).update(
            status=DeviceGrant.Status.REVOKED, revoked_at=now
        )


def revoke_device_grant(grant):
    from django.utils import timezone

    from apps.accounts.models_devices import DeviceGrant

    now = timezone.now()
    DeviceGrant.objects.filter(pk=grant.pk).update(
        status=DeviceGrant.Status.REVOKED, revoked_at=now
    )
    for family in grant.refresh_families.filter(revoked_at__isnull=True):
        blacklist_device_family(family)
    try:
        from apps.integrations.models_push import PushDevice

        PushDevice.objects.filter(device_grant=grant, active=True).update(
            active=False, invalidated_at=now
        )
    except (ImportError, LookupError):
        pass
