"""
Sign in with Apple identity token verification
"""

from dataclasses import dataclass
from typing import Optional

import jwt
from jwt import PyJWKClient

from app.config import settings

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"

# Cached JWKS client; keys are fetched lazily and reused.
_jwk_client = PyJWKClient(APPLE_KEYS_URL, cache_keys=True)


class AppleTokenError(Exception):
    """Raised when an Apple identity token cannot be verified"""


@dataclass
class AppleIdentity:
    sub: str
    email: Optional[str]


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

    return AppleIdentity(sub=sub, email=payload.get("email"))
