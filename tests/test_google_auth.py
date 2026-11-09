"""
Sign in with Google (web, Google Identity Services ID token) tests
"""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings
from app.core import google
from app.models import User

CLIENT_ID = "1234-web.apps.googleusercontent.com"
IOS_CLIENT_ID = "1234-ios.apps.googleusercontent.com"


@pytest.fixture
def google_keys(monkeypatch):
    """Sign tokens with a local RSA key and serve it instead of Google's JWKS."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        google._jwk_client, "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=private_key.public_key())
    )
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "google_ios_client_id", None)

    def make_token(sub="google-sub-1", email="ayse@gmail.com", email_verified=True, aud=CLIENT_ID,
                   iss="https://accounts.google.com", exp_offset=600):
        claims = {"iss": iss, "aud": aud, "sub": sub, "iat": int(time.time()),
                  "exp": int(time.time()) + exp_offset, "email_verified": email_verified}
        if email:
            claims["email"] = email
        return jwt.encode(claims, private_key, algorithm="RS256")

    return make_token


@pytest.mark.auth
class TestGoogleTokenVerification:
    @pytest.mark.parametrize("iss", ["https://accounts.google.com", "accounts.google.com"])
    def test_valid_token(self, google_keys, iss):
        identity = google.verify_id_token(google_keys(iss=iss))
        assert identity.sub == "google-sub-1"
        assert identity.email == "ayse@gmail.com"

    @pytest.mark.parametrize("kwargs", [
        {"aud": "someone-else.apps.googleusercontent.com"},
        {"iss": "https://evil.example.com"},
        {"exp_offset": -60},
        {"email_verified": False},
        {"email": None},
    ])
    def test_rejects_bad_claims(self, google_keys, kwargs):
        with pytest.raises(google.GoogleTokenError):
            google.verify_id_token(google_keys(**kwargs))

    def test_rejects_foreign_signature(self, google_keys):
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = jwt.encode({"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "x",
                             "email": "x@gmail.com", "email_verified": True,
                             "exp": int(time.time()) + 600}, other_key, algorithm="RS256")
        with pytest.raises(google.GoogleTokenError):
            google.verify_id_token(forged)

    def test_accepts_ios_client_audience(self, google_keys, monkeypatch):
        monkeypatch.setattr(settings, "google_ios_client_id", IOS_CLIENT_ID)
        identity = google.verify_id_token(google_keys(aud=IOS_CLIENT_ID))
        assert identity.sub == "google-sub-1"
        google.verify_id_token(google_keys())  # web client keeps working

    def test_ios_audience_rejected_when_unset(self, google_keys, monkeypatch):
        monkeypatch.setattr(settings, "google_ios_client_id", None)
        with pytest.raises(google.GoogleTokenError):
            google.verify_id_token(google_keys(aud=IOS_CLIENT_ID))


@pytest.mark.auth
class TestGoogleSignInEndpoint:
    def test_creates_user_on_first_sign_in(self, client, google_keys, test_db):
        response = client.post("/api/v1/auth/google", json={"credential": google_keys()})
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] and body["refresh_token"]
        assert body["user"]["email"] == "ayse@gmail.com"
        assert body["user"]["has_google"] is True

        user = test_db.query(User).filter(User.email == "ayse@gmail.com").one()
        assert user.google_sub == "google-sub-1"
        assert user.password is None

    def test_same_sub_returns_same_user(self, client, google_keys):
        first = client.post("/api/v1/auth/google", json={"credential": google_keys()}).json()
        second = client.post("/api/v1/auth/google",
                             json={"credential": google_keys(email="renamed@gmail.com")}).json()
        assert first["user"]["id"] == second["user"]["id"]

    def test_links_existing_email_account(self, client, google_keys, test_user, test_db):
        response = client.post("/api/v1/auth/google", json={"credential": google_keys(email=test_user.email.upper())})
        assert response.status_code == 200
        assert response.json()["user"]["id"] == test_user.id
        test_db.refresh(test_user)
        assert test_user.google_sub == "google-sub-1"

    def test_invalid_token_is_unauthorized(self, client, google_keys):
        response = client.post("/api/v1/auth/google", json={"credential": "not-a-jwt"})
        assert response.status_code == 401

    def test_unconfigured_returns_503(self, client, monkeypatch):
        monkeypatch.setattr(settings, "google_client_id", None)
        monkeypatch.setattr(settings, "google_ios_client_id", None)
        response = client.post("/api/v1/auth/google", json={"credential": "anything"})
        assert response.status_code == 503
