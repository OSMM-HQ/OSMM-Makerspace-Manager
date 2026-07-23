from rest_framework.throttling import SimpleRateThrottle


class PasswordResetEmailThrottle(SimpleRateThrottle):
    scope = "password_reset_email"

    def get_cache_key(self, request, view):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return None
        return self.cache_format % {"scope": self.scope, "ident": email}


class MemberVerificationEmailThrottle(SimpleRateThrottle):
    scope = "member_verification_email"

    def get_cache_key(self, request, view):
        email = request.data.get("email") or getattr(request.user, "email", "")
        email = email.strip().lower()
        if not email:
            return None
        return self.cache_format % {"scope": self.scope, "ident": email}


MemberSignUpEmailThrottle = MemberVerificationEmailThrottle


class DeviceLoginThrottle(SimpleRateThrottle):
    scope = "device_login"

    def get_cache_key(self, request, view):
        return self.get_ident(request) and self.cache_format % {
            "scope": self.scope, "ident": self.get_ident(request)
        }


class DeviceLoginUserThrottle(SimpleRateThrottle):
    scope = "device_login_user"

    def get_cache_key(self, request, view):
        from apps.accounts.audit_events import fingerprint

        username = str(request.data.get("username") or "").strip().lower()
        return None if not username else self.cache_format % {
            "scope": self.scope, "ident": fingerprint(username)
        }
