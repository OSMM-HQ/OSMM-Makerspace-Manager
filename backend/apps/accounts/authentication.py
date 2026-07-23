from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.accounts.models import User
from apps.accounts.models_devices import DeviceGrant, DeviceRefreshFamily


class SpaceWorksJWTAuthentication(JWTAuthentication):
    """Adds immediate device-grant checks while preserving ordinary JWT behavior."""

    def authenticate(self, request):
        authenticated = super().authenticate(request)
        if authenticated is None:
            return None
        user, token = authenticated
        grant_id = token.get("device_grant_id")
        if grant_id is None:
            if request.headers.get("X-Makerspace-Id") is not None:
                raise PermissionDenied("Native makerspace selection requires a device grant.")
            return authenticated
        family_id = token.get("device_family_id")
        if not family_id:
            raise AuthenticationFailed("Invalid device authorization.")
        grant = DeviceGrant.objects.filter(pk=grant_id, user=user).first()
        valid = bool(
            grant and grant.status == DeviceGrant.Status.ACTIVE
            and user.is_active and user.access_status == User.AccessStatus.ACTIVE
            and DeviceRefreshFamily.objects.filter(
                pk=family_id, grant=grant, user=user, revoked_at__isnull=True
            ).exists()
        )
        if not valid:
            raise AuthenticationFailed("Device authorization is no longer active.")
        request.device_grant = grant
        from apps.makerspaces.origin_scope import validate_native_makerspace_scope

        validate_native_makerspace_scope(request, user, grant)
        DeviceGrant.objects.filter(pk=grant.pk).update(last_used_at=timezone.now())
        return user, token


# Preserve SimpleJWT's documented Bearer security scheme after replacing its
# authenticator with the device-grant-aware subclass above.
from drf_spectacular.contrib.rest_framework_simplejwt import (  # noqa: E402
    SimpleJWTScheme,
)


class SpaceWorksJWTScheme(SimpleJWTScheme):
    target_class = "apps.accounts.authentication.SpaceWorksJWTAuthentication"
