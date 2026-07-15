from django.http import HttpResponseBadRequest

from apps.makerspaces import domain_verification, hosting


class TenantHostValidationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if domain_verification.is_self_host():
            return self.get_response(request)
        raw_host = request.META.get("HTTP_HOST", "")
        if not hosting.host_is_allowed(raw_host):
            return HttpResponseBadRequest("Invalid host.")
        return self.get_response(request)
