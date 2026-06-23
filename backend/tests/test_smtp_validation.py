import pytest
from django.test import override_settings

from apps.admin_api.api_client_serializers import ApiIntegrationSettingsSerializer
from apps.admin_api.serializers_makerspaces import MakerspaceSerializer
from apps.admin_api.views_platform import PlatformEmailSettingsSerializer
from apps.integrations.admin import PlatformEmailSettingsAdminForm
from apps.integrations.dispatch import dispatch_email
from apps.integrations.models import EmailLog, PlatformEmailSettings
from apps.integrations.smtp_validation import validate_smtp_endpoint
from apps.makerspaces.models import Makerspace

pytestmark = pytest.mark.django_db


def public_dns(monkeypatch, address="8.8.8.8"):
    monkeypatch.setattr(
        "apps.integrations.smtp_validation.socket.getaddrinfo",
        lambda host, port, type=None: [(None, None, None, None, (address, port))],
    )


@pytest.mark.parametrize("port", [25, 465, 587, 2525])
def test_public_smtp_ports_are_allowed(monkeypatch, port):
    public_dns(monkeypatch)

    validate_smtp_endpoint("smtp.public.example", port)


@pytest.mark.parametrize("host", ["127.0.0.1", "10.0.0.4", "172.16.1.5", "192.168.1.10"])
def test_private_smtp_host_is_rejected_by_default(host):
    with pytest.raises(Exception) as exc:
        validate_smtp_endpoint(host, 587)

    assert "smtp_host" in str(exc.value)


@override_settings(DEBUG=True, ALLOW_PRIVATE_SMTP_HOSTS=True)
def test_private_smtp_host_requires_debug_bypass():
    validate_smtp_endpoint("127.0.0.1", 1025)


@override_settings(DEBUG=True, ALLOW_PRIVATE_SMTP_HOSTS=False)
def test_debug_without_private_smtp_flag_still_rejects_private_host():
    with pytest.raises(Exception):
        validate_smtp_endpoint("127.0.0.1", 587)


def test_makerspace_serializer_rejects_private_smtp_host():
    space = Makerspace.objects.create(name="smtp-write-space", slug="smtp-write-space")
    serializer = MakerspaceSerializer(
        instance=space,
        data={"smtp_host": "127.0.0.1", "smtp_port": 587},
        partial=True,
    )

    assert serializer.is_valid() is False
    assert "smtp_host" in serializer.errors


def test_platform_serializer_rejects_private_smtp_host():
    settings_obj = PlatformEmailSettings.load()
    serializer = PlatformEmailSettingsSerializer(
        instance=settings_obj,
        data={"smtp_host": "127.0.0.1", "smtp_port": 587},
        partial=True,
    )

    assert serializer.is_valid() is False
    assert "smtp_host" in serializer.errors


def test_api_client_settings_serializer_rejects_private_smtp_host():
    space = Makerspace.objects.create(name="smtp-api-client", slug="smtp-api-client")
    serializer = ApiIntegrationSettingsSerializer(
        instance=space,
        data={"smtp_host": "127.0.0.1", "smtp_port": 587},
        partial=True,
    )

    assert serializer.is_valid() is False
    assert "smtp_host" in serializer.errors


def test_platform_admin_form_rejects_private_smtp_host():
    form = PlatformEmailSettingsAdminForm(
        data={"smtp_host": "127.0.0.1", "smtp_port": 587, "from_email": ""},
        instance=PlatformEmailSettings.load(),
    )

    assert form.is_valid() is False
    assert "smtp_host" in form.errors


def test_delivery_rechecks_dns_and_stores_sanitized_error(monkeypatch):
    public_dns(monkeypatch, "10.1.2.3")
    space = Makerspace.objects.create(
        name="smtp-delivery-private",
        slug="smtp-delivery-private",
        smtp_host="smtp.internal.example",
        smtp_port=587,
    )

    log = dispatch_email(
        to_email="borrower@example.com",
        subject="Ready",
        text_body="Body",
        makerspace=space,
        sync=True,
    )

    log.refresh_from_db()
    assert log.status == EmailLog.Status.FAILED
    assert log.error == "email_delivery_failed:ValidationError"
    assert "smtp.internal" not in log.error
