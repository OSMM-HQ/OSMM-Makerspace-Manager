from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import User


def user_payload(user, request=None):
    from apps.accounts import rbac
    from apps.makerspaces.origin_scope import origin_scoped_makerspace_id

    memberships = user.makerspace_memberships.select_related("makerspace")
    archived_ids = rbac.archived_makerspace_ids()
    if archived_ids:
        memberships = memberships.exclude(makerspace_id__in=archived_ids)
    memberships = rbac.hide_from_superadmin(user, memberships, field="makerspace_id")
    if request is not None:
        scoped_makerspace_id = origin_scoped_makerspace_id(request)
        if scoped_makerspace_id is not None:
            memberships = memberships.filter(makerspace_id=scoped_makerspace_id)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_superuser": user.is_superuser,
        "must_change_password": user.must_change_password,
        "makerspaces": [
            {"id": m.makerspace_id, "slug": m.makerspace.slug, "role": m.role}
            for m in memberships
        ],
    }


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)  # raises AuthenticationFailed on bad creds/inactive
        if self.user.access_status != User.AccessStatus.ACTIVE:
            raise AuthenticationFailed("Account access is restricted.", code="access_denied")
        data["user"] = user_payload(self.user, request=self.context.get("request"))
        return data
