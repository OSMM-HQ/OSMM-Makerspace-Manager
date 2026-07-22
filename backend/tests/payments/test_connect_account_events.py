from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.payments.connect import refresh_connected_account
from apps.payments.models import (
    MakerspacePaymentSettings,
    PlatformStripeConnectSettings,
    ProcessedStripeEvent,
)
from apps.payments.services import apply_connect_webhook_event
from tests.return_helpers import make_space


pytestmark = pytest.mark.django_db


def _platform_settings():
    platform = PlatformStripeConnectSettings.load()
    platform.set_stripe_secret_key("sk_platform")
    platform.set_stripe_webhook_secret("whsec_platform")
    platform.stripe_connect_client_id = "ca_platform"
    platform.save()


def _merchant(slug, *, status=MakerspacePaymentSettings.ConnectStatus.ACTIVE):
    makerspace = make_space(slug)
    return MakerspacePaymentSettings.objects.create(
        makerspace=makerspace,
        connect_account_id=f"acct_{slug.replace('-', '')}",
        connect_status=status,
        connect_charges_enabled=status == MakerspacePaymentSettings.ConnectStatus.ACTIVE,
        connect_payouts_enabled=status == MakerspacePaymentSettings.ConnectStatus.ACTIVE,
    )


def _account_event(event_id, event_type, merchant, **payload):
    return {
        "id": event_id,
        "created": payload.pop("created", int(timezone.now().timestamp()) + 1),
        "account": merchant.connect_account_id,
        "type": event_type,
        "data": {"object": {"id": merchant.connect_account_id, **payload}},
    }


def test_refresh_only_persists_connect_status_fields(monkeypatch):
    merchant = _merchant(
        "refresh-partial", status=MakerspacePaymentSettings.ConnectStatus.PENDING
    )
    merchant.stripe_publishable_key = "pk_old"
    merchant.default_currency = "usd"
    merchant.set_stripe_secret_key("sk_old")
    merchant.set_stripe_webhook_secret("whsec_old")
    merchant.save()

    def fetch(_account_id):
        concurrent = MakerspacePaymentSettings.objects.get(pk=merchant.pk)
        concurrent.stripe_publishable_key = "pk_new"
        concurrent.set_stripe_secret_key("sk_new")
        concurrent.set_stripe_webhook_secret("whsec_new")
        concurrent.default_currency = "inr"
        concurrent.connect_account_id = "acct_refreshreplaced"
        concurrent.save()
        return {
            "charges_enabled": True,
            "payouts_enabled": True,
            "details_submitted": True,
        }

    monkeypatch.setattr("apps.payments.connect.fetch_account", fetch)
    refresh_connected_account(merchant)

    merchant.refresh_from_db()
    assert merchant.connect_status == MakerspacePaymentSettings.ConnectStatus.ACTIVE
    assert merchant.connect_charges_enabled is True
    assert merchant.connect_payouts_enabled is True
    assert merchant.connect_account_id == "acct_refreshreplaced"
    assert merchant.stripe_publishable_key == "pk_new"
    assert merchant.get_stripe_secret_key() == "sk_new"
    assert merchant.get_stripe_webhook_secret() == "whsec_new"
    assert merchant.default_currency == "inr"


def test_account_updated_uses_authoritative_refresh_not_event_payload(monkeypatch):
    _platform_settings()
    merchant = _merchant("authoritative-update")
    event = _account_event(
        "evt_stale_active",
        "account.updated",
        merchant,
        charges_enabled=True,
        payouts_enabled=True,
        details_submitted=True,
    )
    monkeypatch.setattr(
        "apps.payments.connect.fetch_account",
        lambda _account_id: {
            "charges_enabled": False,
            "payouts_enabled": False,
            "details_submitted": True,
        },
    )

    apply_connect_webhook_event(event)

    merchant.refresh_from_db()
    assert merchant.connect_status == MakerspacePaymentSettings.ConnectStatus.RESTRICTED
    assert merchant.connect_charges_enabled is False
    assert merchant.connect_payouts_enabled is False


def test_account_updated_refresh_failure_fails_closed_and_is_idempotent(monkeypatch):
    from apps.payments.stripe_client import PaymentsUnavailable

    _platform_settings()
    merchant = _merchant("refresh-failure")
    calls = []

    def unavailable(account_id):
        calls.append(account_id)
        raise PaymentsUnavailable("unavailable")

    monkeypatch.setattr("apps.payments.connect.fetch_account", unavailable)
    event = _account_event("evt_refresh_failure", "account.updated", merchant)

    apply_connect_webhook_event(event)
    apply_connect_webhook_event(event)

    merchant.refresh_from_db()
    assert merchant.connect_status == MakerspacePaymentSettings.ConnectStatus.RESTRICTED
    assert merchant.connect_charges_enabled is False
    assert merchant.connect_payouts_enabled is False
    assert calls == [merchant.connect_account_id]
    assert ProcessedStripeEvent.objects.filter(
        makerspace=merchant.makerspace, stripe_event_id="evt_refresh_failure"
    ).count() == 1


def test_deauthorization_is_terminal_against_late_account_update(monkeypatch):
    _platform_settings()
    merchant = _merchant("deauth-ordering")
    deauthorized = _account_event(
        "evt_deauthorized", "account.application.deauthorized", merchant
    )
    stale_update = _account_event(
        "evt_late_update",
        "account.updated",
        merchant,
        charges_enabled=True,
        payouts_enabled=True,
        details_submitted=True,
    )
    refreshes = []
    monkeypatch.setattr(
        "apps.payments.connect.fetch_account",
        lambda account_id: refreshes.append(account_id),
    )

    apply_connect_webhook_event(deauthorized)
    apply_connect_webhook_event(stale_update)
    apply_connect_webhook_event(deauthorized)
    apply_connect_webhook_event(stale_update)

    merchant.refresh_from_db()
    assert merchant.connect_status == MakerspacePaymentSettings.ConnectStatus.DISCONNECTED
    assert merchant.connect_charges_enabled is False
    assert merchant.connect_payouts_enabled is False
    assert refreshes == []
    assert ProcessedStripeEvent.objects.filter(makerspace=merchant.makerspace).count() == 2


def test_delayed_deauthorization_cannot_disconnect_same_account_reonboarding():
    merchant = _merchant("deauth-stale-reonboarding")
    reonboarded_at = timezone.now()
    MakerspacePaymentSettings.objects.filter(pk=merchant.pk).update(
        connect_account_assigned_at=reonboarded_at
    )
    delayed = _account_event(
        "evt_delayed_deauthorization",
        "account.application.deauthorized",
        merchant,
        created=int((reonboarded_at - timedelta(minutes=5)).timestamp()),
    )

    apply_connect_webhook_event(delayed)

    merchant.refresh_from_db()
    assert merchant.connect_status == MakerspacePaymentSettings.ConnectStatus.ACTIVE
    assert merchant.connect_charges_enabled is True
    assert merchant.connect_payouts_enabled is True
    assert ProcessedStripeEvent.objects.filter(
        makerspace=merchant.makerspace,
        stripe_event_id="evt_delayed_deauthorization",
    ).exists()
    assert AuditLog.objects.filter(
        action="payments.connect_deauthorization_ignored",
        makerspace=merchant.makerspace,
    ).exists()


def test_delayed_deauthorization_cannot_disconnect_new_account_assignment():
    previous_owner = _merchant("deauth-previous-owner")
    reassigned_account_id = previous_owner.connect_account_id
    MakerspacePaymentSettings.objects.filter(pk=previous_owner.pk).update(
        connect_account_id=None,
        connect_status=MakerspacePaymentSettings.ConnectStatus.DISCONNECTED,
        connect_charges_enabled=False,
        connect_payouts_enabled=False,
    )
    current_owner = _merchant("deauth-current-owner")
    assigned_at = timezone.now()
    MakerspacePaymentSettings.objects.filter(pk=current_owner.pk).update(
        connect_account_id=reassigned_account_id,
        connect_account_assigned_at=assigned_at,
    )
    current_owner.refresh_from_db()
    delayed = _account_event(
        "evt_delayed_after_reassignment",
        "account.application.deauthorized",
        current_owner,
        created=int((assigned_at - timedelta(minutes=10)).timestamp()),
    )

    apply_connect_webhook_event(delayed)

    current_owner.refresh_from_db()
    assert current_owner.connect_status == MakerspacePaymentSettings.ConnectStatus.ACTIVE
    assert current_owner.connect_charges_enabled is True
    assert current_owner.connect_payouts_enabled is True
    assert AuditLog.objects.filter(
        action="payments.connect_deauthorization_ignored",
        makerspace=current_owner.makerspace,
    ).exists()


def test_deauthorization_in_assignment_second_is_not_hidden_by_later_refresh():
    merchant = _merchant("deauth-same-second")
    assigned_at = timezone.now()
    refreshed_at = assigned_at + timedelta(microseconds=500000)
    MakerspacePaymentSettings.objects.filter(pk=merchant.pk).update(
        connect_account_assigned_at=assigned_at,
        connect_status_updated_at=refreshed_at,
    )
    event = _account_event(
        "evt_deauth_same_second",
        "account.application.deauthorized",
        merchant,
        created=int(assigned_at.timestamp()),
    )

    apply_connect_webhook_event(event)

    merchant.refresh_from_db()
    assert merchant.connect_status == MakerspacePaymentSettings.ConnectStatus.DISCONNECTED
    assert AuditLog.objects.filter(
        action="payments.connect_deauthorized",
        makerspace=merchant.makerspace,
    ).exists()
