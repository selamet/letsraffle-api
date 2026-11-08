"""
Sign in with Google ID token verification (Google Identity Services on the web)
"""

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from app.config import settings

GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_KEYS_URL = "https://www.googleapis.com/oauth2/v3/certs"

# Cached JWKS client; keys are fetched lazily and reused.
_jwk_client = PyJWKClient(GOOGLE_KEYS_URL, cache_keys=True)


class GoogleTokenError(Exception):
    """Raised when a Google ID token cannot be verified"""


@dataclass
class GoogleIdentity:
    sub: str
    email: str


def verify_id_token(id_token: str) -> GoogleIdentity:
    """
    Verify a Google ID token (RS256) and return its subject and verified email.

    Checks signature against Google's JWKS, issuer, audience (web client ID), expiry and
    that Google has verified the email — accounts are linked by email, so an unverified
    address must never be trusted.
    """
    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(id_token)
        payload = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.google_client_id,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except Exception as exc:  # PyJWT and network errors are all treated as invalid tokens
        raise GoogleTokenError(str(exc)) from exc

    if payload.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleTokenError("Unexpected issuer")

    email = payload.get("email")
    if not email or payload.get("email_verified") is not True:
        raise GoogleTokenError("Token has no verified email")

    return GoogleIdentity(sub=payload["sub"], email=email)
