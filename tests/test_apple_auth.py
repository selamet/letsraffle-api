"""
Sign in with Apple and account (me / delete) endpoint tests
"""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core import apple
from app.models import User
from app.models.draw import Draw


@pytest.fixture
def apple_keys(monkeypatch):
    """Sign tokens with a local RSA key and serve it instead of Apple's JWKS."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        apple._jwk_client, "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=private_key.public_key())
    )

    def make_token(sub="apple-sub-1", email="ayse@privaterelay.appleid.com", aud="com.letsraffle.ios",
                   iss=apple.APPLE_ISSUER, exp_offset=600):
        claims = {"iss": iss, "aud": aud, "sub": sub, "iat": int(time.time()), "exp": int(time.time()) + exp_offset}
        if email:
            claims["email"] = email
        return jwt.encode(claims, private_key, algorithm="RS256")

    return make_token


@pytest.mark.auth
class TestAppleTokenVerification:
    def test_valid_token(self, apple_keys):
        identity = apple.verify_identity_token(apple_keys())
        assert identity.sub == "apple-sub-1"
        assert identity.email == "ayse@privaterelay.appleid.com"

    @pytest.mark.parametrize("kwargs", [
        {"aud": "com.someone.else"},
        {"iss": "https://evil.example.com"},
        {"exp_offset": -60},
    ])
    def test_rejects_wrong_claims(self, apple_keys, kwargs):
        with pytest.raises(apple.AppleTokenError):
            apple.verify_identity_token(apple_keys(**kwargs))

    def test_accepts_web_services_id_when_configured(self, apple_keys, monkeypatch):
        monkeypatch.setattr(apple.settings, "apple_services_id", "com.letsraffle.web")
        identity = apple.verify_identity_token(apple_keys(aud="com.letsraffle.web"))
        assert identity.sub == "apple-sub-1"
        # The iOS bundle id keeps working alongside it
        apple.verify_identity_token(apple_keys())

    def test_rejects_web_audience_when_services_id_unset(self, apple_keys, monkeypatch):
        monkeypatch.setattr(apple.settings, "apple_services_id", None)
        with pytest.raises(apple.AppleTokenError):
            apple.verify_identity_token(apple_keys(aud="com.letsraffle.web"))

    def test_rejects_foreign_signature(self, apple_keys):
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = jwt.encode({"iss": apple.APPLE_ISSUER, "aud": "com.letsraffle.ios", "sub": "x",
                             "exp": int(time.time()) + 600}, other_key, algorithm="RS256")
        with pytest.raises(apple.AppleTokenError):
            apple.verify_identity_token(forged)


@pytest.mark.auth
class TestAppleSignIn:
    def test_creates_user_on_first_sign_in(self, client, apple_keys, test_db):
        response = client.post("/api/v1/auth/apple", json={"identity_token": apple_keys(), "first_name": "Ayşe"})

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"]
        assert data["user"]["email"] == "ayse@privaterelay.appleid.com"
        assert data["user"]["has_apple"] is True
        user = test_db.query(User).filter(User.apple_sub == "apple-sub-1").one()
        assert user.password is None

    def test_same_sub_returns_same_user_even_without_email(self, client, apple_keys):
        first = client.post("/api/v1/auth/apple", json={"identity_token": apple_keys()}).json()
        second = client.post("/api/v1/auth/apple", json={"identity_token": apple_keys(email=None)}).json()
        assert first["user"]["id"] == second["user"]["id"]

    def test_links_existing_email_account(self, client, apple_keys, test_user):
        response = client.post("/api/v1/auth/apple", json={"identity_token": apple_keys(email=test_user.email)})

        assert response.status_code == 200
        assert response.json()["user"]["id"] == test_user.id
        assert response.json()["user"]["has_apple"] is True

    def test_unknown_user_without_email_is_rejected(self, client, apple_keys):
        response = client.post("/api/v1/auth/apple", json={"identity_token": apple_keys(email=None)})
        assert response.status_code == 400

    def test_invalid_token_is_unauthorized(self, client):
        response = client.post("/api/v1/auth/apple", json={"identity_token": "not-a-jwt"})
        assert response.status_code == 401

    def test_apple_only_user_cannot_use_password_login(self, client, apple_keys):
        client.post("/api/v1/auth/apple", json={"identity_token": apple_keys()})
        response = client.post("/api/v1/auth/login", json={"email": "ayse@privaterelay.appleid.com", "password": ""})
        assert response.status_code == 401


@pytest.mark.auth
class TestAccount:
    def test_get_me(self, client, auth_headers, test_user):
        response = client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["email"] == test_user.email
        assert response.json()["has_apple"] is False

    def test_me_requires_auth(self, client):
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_delete_me_keeps_draws_detached(self, client, auth_headers, test_user, test_db):
        create = client.post("/api/v1/draws/dynamic", headers=auth_headers, json={
            "participants": [{"firstName": "Org", "lastName": "Test", "email": "org@test.com"}]
        })
        draw_id = create.json()["drawId"]

        response = client.delete("/api/v1/auth/me", headers=auth_headers)

        assert response.status_code == 204
        test_db.expire_all()
        assert test_db.query(User).filter(User.id == test_user.id).first() is None
        assert test_db.query(Draw).filter(Draw.id == draw_id).one().creator_id is None
