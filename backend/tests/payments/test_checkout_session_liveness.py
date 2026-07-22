from apps.payments import stripe_client
from apps.payments.resolution import PaymentSource


def test_expire_accepts_an_already_closed_session_after_authoritative_retrieval(
    monkeypatch,
):
    calls = []

    class Sessions:
        def expire(self, session_id, *, options):
            calls.append(("expire", session_id, options))
            raise RuntimeError("session is already expired")

        def retrieve(self, session_id, *, options):
            calls.append(("retrieve", session_id, options))
            return {"status": "expired"}

    class FakeStripe:
        class StripeClient:
            def __init__(self, *, api_key):
                assert api_key == "sk_platform"
                self.v1 = type(
                    "V1",
                    (),
                    {"checkout": type("Checkout", (), {"sessions": Sessions()})()},
                )()

    monkeypatch.setattr(stripe_client, "_stripe_module", lambda: FakeStripe)
    source = PaymentSource(
        provider="connect",
        secret_key="sk_platform",
        webhook_secret="whsec_platform",
        connected_account_id="acct_closed",
    )

    assert stripe_client.expire_checkout_session(source, "cs_closed") is True
    assert calls == [
        ("expire", "cs_closed", {"stripe_account": "acct_closed"}),
        ("retrieve", "cs_closed", {"stripe_account": "acct_closed"}),
    ]


def test_expire_keeps_session_unconfirmed_when_retrieval_is_ambiguous(monkeypatch):
    class Sessions:
        def expire(self, session_id, *, options):
            raise RuntimeError("expiry response lost")

        def retrieve(self, session_id, *, options):
            raise TimeoutError("Stripe status unavailable")

    class FakeStripe:
        class StripeClient:
            def __init__(self, *, api_key):
                self.v1 = type(
                    "V1",
                    (),
                    {"checkout": type("Checkout", (), {"sessions": Sessions()})()},
                )()

    monkeypatch.setattr(stripe_client, "_stripe_module", lambda: FakeStripe)
    source = PaymentSource(
        provider="connect",
        secret_key="sk_platform",
        webhook_secret="whsec_platform",
        connected_account_id="acct_ambiguous",
    )

    assert (
        stripe_client.expire_checkout_session(source, "cs_ambiguous")
        is False
    )


def test_completed_session_is_not_treated_as_safely_expired(monkeypatch):
    class Sessions:
        def retrieve(self, session_id, *, options):
            return {"status": "complete"}

    class FakeStripe:
        class StripeClient:
            def __init__(self, *, api_key):
                self.v1 = type(
                    "V1",
                    (),
                    {"checkout": type("Checkout", (), {"sessions": Sessions()})()},
                )()

    monkeypatch.setattr(stripe_client, "_stripe_module", lambda: FakeStripe)
    source = PaymentSource(
        provider="connect",
        secret_key="sk_platform",
        webhook_secret="whsec_platform",
        connected_account_id="acct_complete",
    )

    assert stripe_client.checkout_session_is_closed(source, "cs_complete") is False
