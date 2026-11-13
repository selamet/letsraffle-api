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


@pytest.fixture
def apple_signin_key(monkeypatch):
    """Configure a throwaway Sign in with Apple key; returns its public key."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    monkeypatch.setattr(apple.settings, "apple_team_id", "TEAM123456")
    monkeypatch.setattr(apple.settings, "apple_signin_key_id", "KEY1234567")
    monkeypatch.setattr(apple.settings, "apple_signin_key", pem.replace("\n", "\\n"))
    return private_key.public_key()


@pytest.mark.auth
class TestAppleTokenManagement:
    """Exchange and revocation calls made to Apple (transport is mocked)"""

    def test_disabled_without_key(self, monkeypatch):
        monkeypatch.setattr(apple.settings, "apple_signin_key", None)

        assert apple.token_management_enabled() is False
        assert apple.exchange_authorization_code("code", "com.letsraffle.ios") is None
        assert apple.revoke_refresh_token("token", "com.letsraffle.ios") is False

    def test_exchange_sends_signed_client_secret(self, apple_signin_key):
        import httpx
        from urllib.parse import parse_qs

        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["form"] = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            return httpx.Response(200, json={"refresh_token": "r.apple-refresh"})

        token = apple.exchange_authorization_code(
            "auth-code", "com.letsraffle.ios", transport=httpx.MockTransport(handler)
        )

        assert token == "r.apple-refresh"
        assert seen["url"] == apple.APPLE_TOKEN_URL
        assert seen["form"]["code"] == "auth-code"
        assert seen["form"]["grant_type"] == "authorization_code"
        assert seen["form"]["client_id"] == "com.letsraffle.ios"

        secret = seen["form"]["client_secret"]
        assert jwt.get_unverified_header(secret)["kid"] == "KEY1234567"
        claims = jwt.decode(secret, apple_signin_key, algorithms=["ES256"], audience=apple.APPLE_ISSUER)
        assert claims["iss"] == "TEAM123456"
        assert claims["sub"] == "com.letsraffle.ios"

    def test_exchange_returns_none_when_apple_refuses(self, apple_signin_key):
        import httpx

        transport = httpx.MockTransport(lambda request: httpx.Response(400, json={"error": "invalid_grant"}))

        assert apple.exchange_authorization_code("used-code", "com.letsraffle.ios", transport=transport) is None

    def test_revoke(self, apple_signin_key):
        import httpx
        from urllib.parse import parse_qs

        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["form"] = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            return httpx.Response(200)

        assert apple.revoke_refresh_token(
            "r.apple-refresh", "com.letsraffle.ios", transport=httpx.MockTransport(handler)
        ) is True
        assert seen["url"] == apple.APPLE_REVOKE_URL
        assert seen["form"]["token"] == "r.apple-refresh"
        assert seen["form"]["token_type_hint"] == "refresh_token"
        assert seen["form"]["client_id"] == "com.letsraffle.ios"

    def test_revoke_reports_failure(self, apple_signin_key):
        import httpx

        def handler(request):
            raise httpx.ConnectError("unreachable")

        assert apple.revoke_refresh_token(
            "r.apple-refresh", "com.letsraffle.ios", transport=httpx.MockTransport(handler)
        ) is False


@pytest.mark.auth
class TestAppleRevocationOnDelete:
    """The refresh token is stored at sign-in and revoked when the account is deleted"""

    def _sign_in(self, client, apple_keys, **extra):
        response = client.post("/api/v1/auth/apple", json={"identity_token": apple_keys(), **extra})
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_sign_in_with_code_stores_refresh_token(self, client, apple_keys, test_db, monkeypatch):
        calls = []
        monkeypatch.setattr(
            apple, "exchange_authorization_code",
            lambda code, client_id: calls.append((code, client_id)) or "r.apple-refresh",
        )

        self._sign_in(client, apple_keys, authorization_code="auth-code")

        user = test_db.query(User).filter(User.apple_sub == "apple-sub-1").first()
        assert calls == [("auth-code", "com.letsraffle.ios")]
        assert user.apple_refresh_token == "r.apple-refresh"
        assert user.apple_client_id == "com.letsraffle.ios"

    def test_sign_in_without_code_does_not_call_apple(self, client, apple_keys, test_db, monkeypatch):
        monkeypatch.setattr(
            apple, "exchange_authorization_code",
            lambda code, client_id: pytest.fail("exchange must not be called"),
        )

        self._sign_in(client, apple_keys)

        user = test_db.query(User).filter(User.apple_sub == "apple-sub-1").first()
        assert user.apple_refresh_token is None

    def test_sign_in_succeeds_when_exchange_fails(self, client, apple_keys, test_db, monkeypatch):
        monkeypatch.setattr(apple, "exchange_authorization_code", lambda code, client_id: None)

        self._sign_in(client, apple_keys, authorization_code="used-code")

        user = test_db.query(User).filter(User.apple_sub == "apple-sub-1").first()
        assert user is not None
        assert user.apple_refresh_token is None

    def test_later_sign_in_without_code_keeps_stored_token(self, client, apple_keys, test_db, monkeypatch):
        monkeypatch.setattr(apple, "exchange_authorization_code", lambda code, client_id: "r.apple-refresh")
        self._sign_in(client, apple_keys, authorization_code="auth-code")

        self._sign_in(client, apple_keys)

        user = test_db.query(User).filter(User.apple_sub == "apple-sub-1").first()
        assert user.apple_refresh_token == "r.apple-refresh"

    def test_delete_revokes_stored_token(self, client, apple_keys, test_db, monkeypatch):
        monkeypatch.setattr(apple, "exchange_authorization_code", lambda code, client_id: "r.apple-refresh")
        revoked = []
        monkeypatch.setattr(
            apple, "revoke_refresh_token",
            lambda token, client_id: revoked.append((token, client_id)) or True,
        )
        headers = self._sign_in(client, apple_keys, authorization_code="auth-code")

        assert client.delete("/api/v1/auth/me", headers=headers).status_code == 204

        assert revoked == [("r.apple-refresh", "com.letsraffle.ios")]
        assert test_db.query(User).filter(User.apple_sub == "apple-sub-1").first() is None

    def test_delete_succeeds_when_revocation_fails(self, client, apple_keys, test_db, monkeypatch):
        monkeypatch.setattr(apple, "exchange_authorization_code", lambda code, client_id: "r.apple-refresh")
        monkeypatch.setattr(apple, "revoke_refresh_token", lambda token, client_id: False)
        headers = self._sign_in(client, apple_keys, authorization_code="auth-code")

        assert client.delete("/api/v1/auth/me", headers=headers).status_code == 204
        assert test_db.query(User).filter(User.apple_sub == "apple-sub-1").first() is None

    def test_delete_without_stored_token_does_not_call_apple(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(
            apple, "revoke_refresh_token",
            lambda token, client_id: pytest.fail("revoke must not be called"),
        )

        assert client.delete("/api/v1/auth/me", headers=auth_headers).status_code == 204

    def test_refresh_token_is_not_exposed(self, client, apple_keys, monkeypatch):
        monkeypatch.setattr(apple, "exchange_authorization_code", lambda code, client_id: "r.apple-refresh")

        response = client.post(
            "/api/v1/auth/apple", json={"identity_token": apple_keys(), "authorization_code": "auth-code"}
        )

        assert "r.apple-refresh" not in response.text
