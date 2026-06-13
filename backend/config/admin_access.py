from django.contrib.auth import logout
from django.http import HttpResponseForbidden
from django.urls import reverse


class AdminSuperuserOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        try:
            prefix = reverse("admin:index")
        except Exception:
            prefix = "/admin/"
        self.admin_prefix = prefix if prefix.endswith("/") else f"{prefix}/"
        self.admin_root = self.admin_prefix.rstrip("/")

    def __call__(self, request):
        if self._is_admin_path(request.path):
            user = getattr(request, "user", None)
            if getattr(user, "is_authenticated", False) and not self._has_access(user):
                # The admin login view authenticates before we can see the user, so an
                # is_staff non-superuser can mint a Django admin session. Flush it here so
                # the stray session can't linger (and the user isn't locked out of logout).
                # The React staff console uses JWT, not this session, so this is safe.
                logout(request)
                return HttpResponseForbidden()
        return self.get_response(request)

    def _is_admin_path(self, path):
        return path == self.admin_root or path.startswith(self.admin_prefix)

    def _has_access(self, user):
        from apps.accounts.models import User

        return bool(
            user.is_active
            and user.is_superuser
            and getattr(user, "access_status", None) == User.AccessStatus.ACTIVE
            # The default super123 seed must rotate before reaching the admin too,
            # otherwise it could bypass the API/staff-console forced-change gate.
            and not getattr(user, "must_change_password", False)
        )


class AdminCspEvalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path_info == "/admin" or request.path_info.startswith("/admin/"):
            # Unfold's standard Alpine build requires unsafe-eval; the Django admin is
            # superuser-gated, so keep this exception scoped to admin responses only.
            merged = dict(getattr(response, "_csp_update", None) or {})
            script_src = merged.get("script-src", [])
            if isinstance(script_src, str):
                script_src = [script_src]
            else:
                script_src = list(script_src)
            if "'unsafe-eval'" not in script_src:
                script_src.append("'unsafe-eval'")
            merged["script-src"] = script_src
            response._csp_update = merged
        return response


class SuperuserOnlyModelAdmin:
    def _has_superuser_access(self, request):
        from apps.accounts.models import User

        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.is_superuser
            and getattr(user, "access_status", None) == User.AccessStatus.ACTIVE
            and not getattr(user, "must_change_password", False)
        )

    def has_view_permission(self, request, obj=None):
        return self._has_superuser_access(request)

    def has_add_permission(self, request):
        return self._has_superuser_access(request)

    def has_change_permission(self, request, obj=None):
        return self._has_superuser_access(request)

    def has_delete_permission(self, request, obj=None):
        return self._has_superuser_access(request)

    def has_module_permission(self, request):
        return self._has_superuser_access(request)
