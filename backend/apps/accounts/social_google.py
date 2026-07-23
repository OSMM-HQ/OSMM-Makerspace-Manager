import hmac

from django.conf import settings

from apps.accounts.social_jwt import SocialTokenError, decode_rs256_token


def verify_google_token(raw_token, *, nonce, audience):
    claims = decode_rs256_token(
        raw_token,
        provider="google",
        jwks_url=settings.SOCIAL_GOOGLE_JWKS_URL,
        issuer=("accounts.google.com", "https://accounts.google.com"),
        audience=audience,
    )
    token_nonce = str(claims.get("nonce") or "")
    subject = str(claims.get("sub") or "")
    if not token_nonce or not hmac.compare_digest(token_nonce, nonce) or not subject:
        raise SocialTokenError("Invalid social identity token.")
    return {
        "sub": subject,
        "email": str(claims.get("email") or "").strip().lower(),
        "email_verified": claims.get("email_verified") is True
        or str(claims.get("email_verified")).lower() == "true",
        "name": str(claims.get("name") or "").strip(),
    }
