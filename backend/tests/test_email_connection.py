from unittest.mock import patch

import pytest

from apps.integrations.email import makerspace_mail_connection
from apps.integrations.models import PlatformEmailSettings
from apps.makerspaces.models import Makerspace

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def public_smtp_dns(monkeypatch):
    monkeypatch.setattr(
        "apps.integrations.smtp_validation.socket.getaddrinfo",
        lambda host, port, type=None: [(None, None, None, None, ("8.8.8.8", port))],
    )


def _connection_kwargs(space):
    # Assert the flags email.py passes to get_connection (independent of the test
    # mail backend, which doesn't expose use_ssl/use_tls).
    with patch("apps.integrations.email.get_connection") as get_connection:
        makerspace_mail_connection(space)
    return get_connection.call_args.kwargs


def test_implicit_ssl_disables_starttls():
    # use_ssl (465) and use_tls (587 STARTTLS) are mutually exclusive; when both
    # flags are set, SSL wins and STARTTLS is turned off.
    space = Makerspace.objects.create(
        name="smtp-ssl",
        slug="smtp-ssl",
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_use_tls=True,
        smtp_use_ssl=True,
    )
    kwargs = _connection_kwargs(space)
    assert kwargs["use_ssl"] is True
    assert kwargs["use_tls"] is False
    assert kwargs["timeout"] == 10


def test_starttls_used_when_ssl_off():
    space = Makerspace.objects.create(
        name="smtp-tls",
        slug="smtp-tls",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_use_tls=True,
        smtp_use_ssl=False,
    )
    kwargs = _connection_kwargs(space)
    assert kwargs["use_ssl"] is False
    assert kwargs["use_tls"] is True
    assert kwargs["timeout"] == 10


def test_no_smtp_host_uses_default_connection_when_platform_email_unconfigured():
    space = Makerspace.objects.create(name="smtp-none", slug="smtp-none")
    connection, from_email = makerspace_mail_connection(space)
    assert connection is None


def test_no_smtp_host_falls_back_to_platform_email():
    cfg = PlatformEmailSettings.load()
    cfg.smtp_host = "platform-smtp.example.com"
    cfg.smtp_port = 2525
    cfg.smtp_username = "platform-user"
    cfg.set_smtp_password("platform-secret")
    cfg.smtp_use_tls = True
    cfg.smtp_use_ssl = False
    cfg.from_email = "platform@example.com"
    cfg.save()
    space = Makerspace.objects.create(name="smtp-platform", slug="smtp-platform")

    with patch("apps.integrations.email.get_connection") as get_connection:
        connection, from_email = makerspace_mail_connection(space)

    assert connection == get_connection.return_value
    assert from_email == "platform@example.com"
    assert get_connection.call_args.kwargs["host"] == "platform-smtp.example.com"
    assert get_connection.call_args.kwargs["username"] == "platform-user"
    assert get_connection.call_args.kwargs["password"] == "platform-secret"
    assert get_connection.call_args.kwargs["timeout"] == 10

