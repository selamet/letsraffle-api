"""
Sign in with Apple: identity token verification, and the token exchange and
revocation that account deletion needs
"""

import logging
import time

from dataclasses import dataclass
from typing import Optional

import httpx
import jwt
from jwt import PyJWKClient

from app.config import settings

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_REVOKE_URL = "https://appleid.apple.com/auth/revoke"
# Apple accepts client secrets valid for up to six months; ours are made per request.
CLIENT_SECRET_TTL = 5 * 60

logger = logging.getLogger(__name__)

# Cached JWKS client; keys are fetched lazily and reused.
_jwk_client = PyJWKClient(APPLE_KEYS_URL, cache_keys=True)


class AppleTokenError(Exception):
    """Raised when an Apple identity token cannot be verified"""


@dataclass
class AppleIdentity:
    sub: str
    email: Optional[str]
    # The client the token was issued to: the iOS bundle id or the web Services ID.
    audience: Optional[str] = None


def verify_identity_token(identity_token: str) -> AppleIdentity:
    """
    Verify an Apple identity token (RS256) and return its subject and email.

    Checks signature against Apple's JWKS, issuer, audience and expiry. The audience is the
    iOS bundle id for the app, or the web Services ID for the Apple JS flow on the website.
    """
    audiences = [settings.apple_bundle_id]
    if settings.apple_services_id:
        audiences.append(settings.apple_services_id)

    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(identity_token)
        payload = jwt.decode(
            identity_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audiences,
            issuer=APPLE_ISSUER,
        )
    except Exception as exc:  # PyJWT and network errors are all treated as invalid tokens
        raise AppleTokenError(str(exc)) from exc

    sub = payload.get("sub")
    if not sub:
        raise AppleTokenError("Token has no subject")

    audience = payload.get("aud")
    if isinstance(audience, list):
        audience = audience[0] if audience else None

    return AppleIdentity(sub=sub, email=payload.get("email"), audience=audience)


def _signing_key() -> Optional[str]:
    key = settings.apple_signin_key
    return key.replace("\\n", "\n") if key else None


def token_management_enabled() -> bool:
    """Whether the Sign in with Apple key is configured, so tokens can be exchanged and revoked."""
    return bool(settings.apple_signin_team_id and settings.apple_signin_key_id and _signing_key())


def _client_secret(client_id: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": settings.apple_signin_team_id,
            "iat": now,
            "exp": now + CLIENT_SECRET_TTL,
            "aud": APPLE_ISSUER,
            "sub": client_id,
        },
        _signing_key(),
        algorithm="ES256",
        headers={"kid": settings.apple_signin_key_id},
    )


def exchange_authorization_code(
    authorization_code: str,
    client_id: str,
    transport: Optional[httpx.BaseTransport] = None,
) -> Optional[str]:
    """
    Trade the one-time authorization code from a sign-in for a refresh token.

    The refresh token is only kept so it can be revoked when the account is deleted.
    Returns None when the key is not configured or Apple refuses the code; signing in
    must not depend on this.
    """
    if not token_management_enabled():
        return None
    try:
        with httpx.Client(timeout=10, transport=transport) as client:
            response = client.post(
                APPLE_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": _client_secret(client_id),
                    "code": authorization_code,
                    "grant_type": "authorization_code",
                },
            )
        if response.status_code != 200:
            logger.warning(f"Apple token exchange failed: status={response.status_code}")
            return None
        return response.json().get("refresh_token")
    except Exception as exc:
        logger.warning(f"Apple token exchange failed: {exc}")
        return None


def revoke_refresh_token(
    refresh_token: str,
    client_id: str,
    transport: Optional[httpx.BaseTransport] = None,
) -> bool:
    """
    Revoke a user's Apple tokens, as App Store guideline 5.1.1(v) requires on account deletion.

    Returns whether Apple confirmed the revocation.
    """
    if not token_management_enabled():
        return False
    try:
        with httpx.Client(timeout=10, transport=transport) as client:
            response = client.post(
                APPLE_REVOKE_URL,
                data={
                    "client_id": client_id,
                    "client_secret": _client_secret(client_id),
                    "token": refresh_token,
                    "token_type_hint": "refresh_token",
                },
            )
        if response.status_code != 200:
            logger.warning(f"Apple token revocation failed: status={response.status_code}")
            return False
        return True
    except Exception as exc:
        logger.warning(f"Apple token revocation failed: {exc}")
        return False
