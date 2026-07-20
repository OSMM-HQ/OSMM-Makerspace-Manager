from rest_framework.permissions import BasePermission

from apps.accounts import rbac
from apps.accounts.models import User
from apps.machines.permissions import IsActiveRequester, active_authenticated as _active_authenticated
from apps.makerspaces.origin_scope import (
    object_in_staff_origin_scope,
    staff_origin_scope_allows,
)


def _active_authenticated(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.access_status == User.AccessStatus.ACTIVE
        and not getattr(user, "must_change_password", False)
    )


class LegacyIsActiveRequester(BasePermission):
    def has_permission(self, request, view):
        return _active_authenticated(getattr(request, "user", None))


class CanManagePrinting(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not _active_authenticated(user) or not staff_origin_scope_allows(request, view):
            return False

        makerspace_id = request.query_params.get("makerspace")
        if makerspace_id is None:
            if getattr(view, "action", None) is not None:
                return bool(
                    rbac.makerspaces_for_action(user, rbac.Action.MANAGE_PRINTING)
                )
            return True
        try:
            makerspace_id = int(makerspace_id)
        except (TypeError, ValueError):
            return False
        return rbac.can(user, rbac.Action.MANAGE_PRINTING, makerspace_id)

    def has_object_permission(self, request, view, obj):
        if not object_in_staff_origin_scope(request, obj):
            return False
        makerspace_id = getattr(obj, "makerspace_id", None)
        if makerspace_id is None and hasattr(obj, "bucket"):
            makerspace_id = obj.bucket.makerspace_id
        return rbac.can(
            request.user,
            rbac.Action.MANAGE_PRINTING,
            makerspace_id,
        )
