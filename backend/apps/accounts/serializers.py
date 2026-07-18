from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import User


def user_payload(user, request=None):
    from apps.accounts import rbac
    from apps.makerspaces.origin_scope import origin_scoped_makerspace_id

    memberships = user.makerspace_memberships.select_related("makerspace", "assigned_role")
    archived_ids = rbac.archived_makerspace_ids()
    if archived_ids:
        memberships = memberships.exclude(makerspace_id__in=archived_ids)
    memberships = rbac.hide_from_superadmin(user, memberships, field="makerspace_id")
    if request is not None:
        scoped_makerspace_id = origin_scoped_makerspace_id(request)
        if scoped_makerspace_id is not None:
            memberships = memberships.filter(makerspace_id=scoped_makerspace_id)

    # Resolve effective actions from the already select_related-loaded membership rows so
    # /auth/login and /auth/me stay O(1) queries — calling rbac.effective_actions() per row
    # would re-query the membership + archived set for each makerspace (1+2N). This mirrors
    # rbac.effective_actions: a superadmin in a VISIBLE makerspace gets the full grantable
    # set; a superadmin who is an explicit member of a hard-hidden makerspace (kept here by
    # hide_from_superadmin's explicit-member carve-out) is membership-limited; everyone else
    # uses the membership's resolved actions. Archived rows are already excluded above.
    is_superadmin = user.is_superuser or user.role == User.Role.SUPERADMIN
    hidden_ids = rbac.superadmin_hidden_makerspace_ids() if is_superadmin else ()

    def _membership_actions(m):
        if is_superadmin and not rbac._id_in(m.makerspace_id, hidden_ids):
            return sorted(rbac.ROLE_GRANTABLE_ACTIONS)
        return sorted(rbac.actions_for_membership(m))

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "phone": user.phone,
        "email_verified": user.email_verified_at is not None,
        "role": user.role,
        "is_superuser": user.is_superuser,
        "must_change_password": user.must_change_password,
        "makerspaces": [
            {
                "id": m.makerspace_id,
                "slug": m.makerspace.slug,
                "role": m.role,
                "role_id": m.assigned_role_id,
                "role_name": (
                    m.assigned_role.name
                    if m.assigned_role_id is not None
                    else _legacy_role_name(m.role)
                ),
                "role_slug": (
                    m.assigned_role.slug
                    if m.assigned_role_id is not None
                    else m.role
                ),
                "actions": _membership_actions(m),
            }
            for m in memberships
        ],
    }


def _legacy_role_name(role):
    from apps.makerspaces.models import MakerspaceMembership

    try:
        return MakerspaceMembership.Role(role).label
    except ValueError:
        return role.replace("_", " ").title()


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        supplied_username = attrs.get(self.username_field, "")
        if supplied_username and not User.objects.filter(username=supplied_username).exists():
            email_matches = User.objects.filter(
                email__iexact=supplied_username, is_active=True
            ).exclude(email="")
            if email_matches.count() == 1:
                attrs[self.username_field] = email_matches.first().username
        data = super().validate(attrs)  # raises AuthenticationFailed on bad creds/inactive
        if self.user.access_status != User.AccessStatus.ACTIVE:
            raise AuthenticationFailed("Account access is restricted.", code="access_denied")
        data["user"] = user_payload(self.user, request=self.context.get("request"))
        return data
