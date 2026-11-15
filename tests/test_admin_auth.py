"""
Admin panel access control: credentials, session token, throttle, guard
"""

import pytest

from app.config import settings
from app.core.admin_auth import (
    admin_enabled,
    create_admin_token,
    is_admin_token,
    login_blocked,
    record_failure,
    reset_failures,
    verify_credentials,
)
from app.core.security import create_access_token, decode_access_token
from app.models import User


@pytest.fixture
def admin_settings(monkeypatch):
    monkeypatch.setattr(settings, "admin_email", "Boss@Example.com")
    monkeypatch.setattr(settings, "admin_password_hash", User.hash_password("s3cret"))
    monkeypatch.setattr(settings, "secret_key", "a-real-secret-key-for-admin-tests")
    reset_failures()
    yield
    reset_failures()


def test_disabled_when_unset(admin_settings, monkeypatch):
    monkeypatch.setattr(settings, "admin_email", None)
    assert admin_enabled() is False


def test_disabled_when_hash_is_not_bcrypt(admin_settings, monkeypatch):
    monkeypatch.setattr(settings, "admin_password_hash", "b$12$mangled")
    assert admin_enabled() is False


def test_disabled_while_secret_key_is_the_published_default(admin_settings, monkeypatch):
    """Anyone can read the default key in the repository and sign their own session with it."""
    monkeypatch.setattr(settings, "secret_key", type(settings).model_fields["secret_key"].default)
    assert admin_enabled() is False
    assert is_admin_token(create_admin_token()) is False


def test_admin_token_without_expiry_rejected(admin_settings):
    import jwt

    forged = jwt.encode({"type": "admin"}, settings.secret_key, algorithm=settings.algorithm)
    assert is_admin_token(forged) is False


def test_enabled_when_configured(admin_settings):
    assert admin_enabled() is True


def test_credentials(admin_settings):
    assert verify_credentials("  boss@example.COM ", "s3cret") is True
    assert verify_credentials("boss@example.com", "wrong") is False
    assert verify_credentials("other@example.com", "s3cret") is False


def test_admin_token_has_no_sub_and_roundtrips(admin_settings):
    token = create_admin_token()
    assert "sub" not in decode_access_token(token)
    assert is_admin_token(token) is True


def test_user_and_participant_tokens_are_not_admin(admin_settings):
    assert is_admin_token(create_access_token({"sub": "a@b.c"})) is False
    assert is_admin_token(create_access_token({"sub": "a@b.c", "type": "participant"})) is False
    assert is_admin_token("garbage") is False
    assert is_admin_token(None) is False


def test_expired_admin_token_rejected(admin_settings, monkeypatch):
    monkeypatch.setattr(settings, "admin_session_hours", -1)
    assert is_admin_token(create_admin_token()) is False


def test_throttle(admin_settings):
    for _ in range(4):
        record_failure()
    assert login_blocked() is False
    record_failure()
    assert login_blocked() is True
    reset_failures()
    assert login_blocked() is False


# --- HTTP layer -------------------------------------------------------------

PAGES = ["/admin", "/admin/draws", "/admin/draws/1", "/admin/users", "/admin/users/1", "/admin/people"]
GOOD_LOGIN = {"email": "admin@example.com", "password": "correct-horse-battery"}


def cors_headers(response):
    return [name for name in response.headers if name.lower().startswith("access-control-")]


def test_panel_is_404_when_unconfigured(client):
    for path in PAGES + ["/admin/login", "/admin/static/admin.css"]:
        assert client.get(path).status_code == 404, path


@pytest.mark.parametrize("path", PAGES)
def test_pages_redirect_to_login_without_session(client, admin_env, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"


def test_login_page_renders(client, admin_env):
    r = client.get("/admin/login")
    assert r.status_code == 200 and 'name="password"' in r.text


def test_static_css_is_served(client, admin_env):
    assert client.get("/admin/static/admin.css").status_code == 200


def test_login_sets_strict_httponly_cookie(client, admin_env):
    r = client.post(
        "/admin/login",
        data={"email": "ADMIN@example.com ", "password": "correct-horse-battery"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/admin"
    c = r.headers["set-cookie"].lower()
    assert "admin_session=" in c and "httponly" in c and "samesite=strict" in c and "path=/admin" in c
    assert "secure" not in c


def test_cookie_is_secure_by_default(client, admin_env, monkeypatch):
    monkeypatch.setattr(settings, "admin_cookie_secure", True)
    r = client.post("/admin/login", data=GOOD_LOGIN, follow_redirects=False)
    assert "secure" in r.headers["set-cookie"].lower()


def test_session_opens_the_panel(admin_client):
    assert admin_client.get("/admin", follow_redirects=False).status_code == 200


def test_wrong_password_then_throttle(client, admin_env):
    bad = {"email": "admin@example.com", "password": "nope"}
    for _ in range(5):
        r = client.post("/admin/login", data=bad)
        assert r.status_code == 401 and "E-posta veya şifre hatalı" in r.text
    assert client.post("/admin/login", data=GOOD_LOGIN, follow_redirects=False).status_code == 429


def test_logout_ends_session(admin_client):
    r = admin_client.post("/admin/logout", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"
    assert admin_client.get("/admin", follow_redirects=False).status_code == 303


def test_tampered_or_expired_cookie_redirects(client, admin_env, monkeypatch):
    client.cookies.set("admin_session", "not-a-jwt")
    assert client.get("/admin", follow_redirects=False).status_code == 303
    monkeypatch.setattr(settings, "admin_session_hours", -1)
    client.cookies.set("admin_session", create_admin_token())
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_user_and_participant_tokens_rejected_by_admin(client, admin_env, auth_token):
    for token in (auth_token, create_access_token({"sub": "x@y.z", "type": "participant"})):
        client.cookies.set("admin_session", token)
        assert client.get("/admin", follow_redirects=False).status_code == 303


def test_admin_token_rejected_by_user_api(client, admin_env, test_user):
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {create_admin_token()}"})
    assert r.status_code == 401


def test_cross_site_requests_rejected(admin_client):
    assert admin_client.get("/admin", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
    assert admin_client.get("/admin", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert admin_client.get("/admin", headers={"Origin": "https://letsraffle.co"}).status_code == 403
    same = {"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"}
    assert admin_client.get("/admin", headers=same).status_code == 200
    assert admin_client.get("/admin", headers={"Sec-Fetch-Site": "none"}).status_code == 200


def test_cross_site_login_post_rejected(client, admin_env):
    r = client.post("/admin/login", data=GOOD_LOGIN, headers={"Origin": "https://evil.example"}, follow_redirects=False)
    assert r.status_code == 403 and "set-cookie" not in r.headers


def test_admin_responses_have_no_cors_and_are_not_cached(admin_client):
    r = admin_client.get("/admin", headers={"Origin": "http://testserver"})
    assert cors_headers(r) == []
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-robots-tag"] == "noindex, nofollow"


def test_admin_preflight_gets_no_cors_headers(client, admin_env):
    pre = client.options("/admin", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert cors_headers(pre) == []


def test_admin_routes_not_in_openapi(client, admin_env):
    assert not [p for p in client.get("/openapi.json").json()["paths"] if p.startswith("/admin")]


def test_following_a_link_from_another_site_is_allowed(client, admin_env):
    """A top-level GET navigation cannot leak the response, so it must not be refused."""
    nav = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
    assert client.get("/admin/login", headers=nav).status_code == 200
    r = client.get("/admin/draws", headers=nav, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"


def test_cross_site_reads_frames_and_posts_stay_refused(admin_client):
    fetch = {"Sec-Fetch-Site": "same-site", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty"}
    assert admin_client.get("/admin/draws", headers=fetch).status_code == 403
    frame = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "iframe"}
    assert admin_client.get("/admin/draws", headers=frame).status_code == 403
    post = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
    assert admin_client.post("/admin/logout", headers=post, follow_redirects=False).status_code == 403
    assert admin_client.get("/admin", follow_redirects=False).status_code == 200


def test_admin_pages_cannot_be_framed(admin_client):
    assert admin_client.get("/admin").headers["x-frame-options"] == "DENY"
