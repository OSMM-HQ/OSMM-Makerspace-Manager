"""Shared requester permissions for public machine-service surfaces."""

from rest_framework.permissions import BasePermission

from apps.accounts.models import User


def active_authenticated(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.access_status == User.AccessStatus.ACTIVE
        and not getattr(user, "must_change_password", False)
    )


class IsActiveRequester(BasePermission):
    def has_permission(self, request, view):
        return active_authenticated(getattr(request, "user", None))
