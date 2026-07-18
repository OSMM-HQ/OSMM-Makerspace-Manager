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
