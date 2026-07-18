import re
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import DailyOtpEmailCounter, EmailVerificationChallenge, User
from apps.accounts import services_registration
from apps.makerspaces import limits

SIGNUP_URL = "/api/v1/auth/member-sign-up"
RESEND_URL = "/api/v1/auth/email-verification/resend"
CONFIRM_URL = "/api/v1/auth/email-verification/confirm"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
ACK = "If the details are valid, a verification email has been sent."
PASSWORD = "Safe member password 947!"


def signup(client, email="member@example.test", **extra):
    return client.post(
        SIGNUP_URL,
        {"display_name": "Member Name", "email": email, "password": PASSWORD, **extra},
        format="json",
    )


def authenticated(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def scan(value, forbidden):
    if isinstance(value, dict):
        return any(scan(item, forbidden) for item in value.values())
    if isinstance(value, list):
        return any(scan(item, forbidden) for item in value)
    return str(value) in forbidden


@pytest.mark.django_db
def test_signup_is_generic_creates_challenge_and_honeypot_does_nothing(monkeypatch):
    codes = []
    monkeypatch.setattr(
        services_registration, "send_email_verification_otp", lambda _, code: codes.append(code) or 1
    )
    client = APIClient()
    response = signup(client)
    assert response.status_code == 200 and response.data == {"detail": ACK}
    user = User.objects.get(email="member@example.test")
    challenge = user.email_challenges.get()
    assert user.is_active and challenge.code_digest != codes[0]
    assert not re.search(re.escape(codes[0]), challenge.code_digest)
    confirm = authenticated(user).post(CONFIRM_URL, {"code": codes[0]}, format="json")
    assert confirm.status_code == 200

    response = signup(client, "bot@example.test", website="https://spam.invalid")
    assert response.status_code == 200 and response.data == {"detail": ACK}
    assert not User.objects.filter(email="bot@example.test").exists()


@pytest.mark.django_db
def test_duplicate_and_weak_signup_behavior(monkeypatch):
    monkeypatch.setattr(services_registration, "send_email_verification_otp", lambda *_: 0)
    client = APIClient()
    assert signup(client, "Member@Example.test").data == {"detail": ACK}
    duplicate = signup(client, "member@example.test")
    assert duplicate.data == {"detail": ACK}
    assert User.objects.filter(email__iexact="member@example.test").count() == 1
    weak = signup(client, "weak@example.test", password="short")
    assert weak.status_code == 400
    assert not User.objects.filter(email="weak@example.test").exists()
    # Weak password on an ALREADY-registered email must also 400 (no existence oracle).
    weak_existing = signup(client, "member@example.test", password="short")
    assert weak_existing.status_code == 400


@pytest.mark.django_db
def test_confirm_expiry_attempt_limit_and_foreign_safety(monkeypatch):
    monkeypatch.setattr(services_registration, "send_email_verification_otp", lambda *_: 0)
    user = User.objects.create_user(username="member-one", email="one@example.test", password=PASSWORD)
    challenge = services_registration.issue_challenge(user)
    other = User.objects.create_user(username="member-two", email="two@example.test", password=PASSWORD)
    # Confirm is scoped to the caller's own challenge, so a foreign account cannot burn
    # the victim's attempts by submitting bad codes.
    bad = authenticated(other).post(CONFIRM_URL, {"code": "000000"}, format="json")
    assert bad.status_code == 400 and bad.data["detail"] == services_registration.GENERIC_CONFIRM_ERROR
    assert EmailVerificationChallenge.objects.get(pk=challenge.pk).failed_attempts == 0

    client = authenticated(user)
    for _ in range(5):
        response = client.post(CONFIRM_URL, {"code": "000000"}, format="json")
        assert response.status_code == 400 and response.data == bad.data
    assert EmailVerificationChallenge.objects.get(pk=challenge.pk).failed_attempts == 5
    # Locked (5 attempts) -> no usable challenge -> same generic error.
    assert client.post(CONFIRM_URL, {"code": "000000"}, format="json").data == bad.data

    # Expiry: a user whose only challenge is expired also gets the generic error.
    stale = User.objects.create_user(username="stale", email="stale@example.test", password=PASSWORD)
    EmailVerificationChallenge.objects.create(
        user=stale, email=stale.email, code_digest=services_registration._digest("123456"),
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    assert authenticated(stale).post(CONFIRM_URL, {"code": "123456"}, format="json").data == bad.data


@pytest.mark.django_db
def test_resend_invalidates_and_confirm_consumes_all_challenges(monkeypatch):
    monkeypatch.setattr(services_registration, "send_email_verification_otp", lambda *_: 1)
    user = User.objects.create_user(username="resend", email="resend@example.test", password=PASSWORD)
    old = services_registration.issue_challenge(user)
    EmailVerificationChallenge.objects.filter(pk=old.pk).update(last_sent_at=timezone.now() - timedelta(minutes=2))
    new = services_registration.issue_challenge(user)
    old.refresh_from_db()
    assert old.consumed_at is not None and new.is_usable(timezone.now())
    # A second active challenge (newest by created_at) proves confirm consumes ALL
    # active challenges for the email, not just the one whose code matched.
    EmailVerificationChallenge.objects.create(
        user=user, email=user.email, code_digest=services_registration._digest("654321"),
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    response = authenticated(user).post(CONFIRM_URL, {"code": "654321"}, format="json")
    assert response.status_code == 200
    assert not EmailVerificationChallenge.objects.filter(user=user, consumed_at__isnull=True).exists()
    user.refresh_from_db()
    assert user.email_verified_at is not None


@pytest.mark.django_db
def test_changing_email_clears_verification():
    user = User.objects.create_user(username="verified", email="old@example.test", password=PASSWORD)
    User.objects.filter(pk=user.pk).update(email_verified_at=timezone.now())
    reloaded = User.objects.get(pk=user.pk)
    assert reloaded.email_verified_at is not None
    reloaded.email = "new@example.test"
    reloaded.save()
    reloaded.refresh_from_db()
    assert reloaded.email == "new@example.test" and reloaded.email_verified_at is None


@pytest.mark.django_db
def test_resend_cooldown_and_login_by_email_or_username(monkeypatch):
    monkeypatch.setattr(services_registration, "send_email_verification_otp", lambda *_: 0)
    user = User.objects.create_user(
        username="legacy-name", email="legacy@example.test", password=PASSWORD,
        display_name="Legacy Member", phone="123",
    )
    services_registration.issue_challenge(user)
    assert authenticated(user).post(RESEND_URL, format="json").data == {"detail": ACK}
    assert user.email_challenges.count() == 1
    assert User.objects.filter(pk=user.pk).exists()
    client = APIClient()
    for identifier in ("legacy@example.test", "legacy-name"):
        response = client.post(LOGIN_URL, {"username": identifier, "password": PASSWORD}, format="json")
        assert response.status_code == 200
        assert response.data["user"]["display_name"] == "Legacy Member"
        assert response.data["user"]["phone"] == "123"
        assert response.data["user"]["email_verified"] is False
    User.objects.filter(pk=user.pk).update(access_status=User.AccessStatus.RESTRICTED)
    assert client.post(LOGIN_URL, {"username": user.email, "password": PASSWORD}, format="json").status_code == 401


@pytest.mark.django_db
def test_managed_otp_quota_and_response_leak_sweep(monkeypatch):
    today = timezone.now().date()
    DailyOtpEmailCounter.objects.filter(day=today).delete()
    monkeypatch.setattr(limits, "is_self_host", lambda: False)
    with override_settings(MANAGED_RESOURCE_LIMITS={"otp_email": 1}):
        assert limits.reserve_platform_otp_quota() is True
        assert limits.reserve_platform_otp_quota() is False
    DailyOtpEmailCounter.objects.filter(day=today).delete()
    dispatched = []
    monkeypatch.setattr(
        services_registration,
        "send_email_verification_otp",
        lambda *_: dispatched.append(True) or 1,
    )
    with override_settings(MANAGED_RESOURCE_LIMITS={"otp_email": 0}):
        capped = services_registration.register_member(
            "Capped", "capped@example.test", "", PASSWORD
        )
    assert capped.email_challenges.exists() and not dispatched
    monkeypatch.setattr(limits, "is_self_host", lambda: True)
    assert limits.reserve_platform_otp_quota() is True

    codes = []
    monkeypatch.setattr(services_registration, "send_email_verification_otp", lambda _, code: codes.append(code) or 1)
    response = signup(APIClient(), "leak@example.test")
    user = User.objects.get(email="leak@example.test")
    challenge = user.email_challenges.get()
    responses = [response.data, authenticated(user).post(RESEND_URL, format="json").data]
    responses.append(authenticated(user).post(CONFIRM_URL, {"code": codes[0]}, format="json").data)
    login = APIClient().post(LOGIN_URL, {"username": user.email, "password": PASSWORD}, format="json")
    responses.extend([login.data, authenticated(user).get(ME_URL).data])
    forbidden = {challenge.code_digest, codes[0], str(challenge.id), "code_digest", "failed_attempts", "expires_at"}
    assert not any(scan(item, forbidden) for item in responses)
