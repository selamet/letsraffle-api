"""
Access control for the read-only admin panel.

There is a single admin, configured through the environment. The session is a
signed cookie that is deliberately unusable against the regular user API.
"""

import hmac
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urlparse

import jwt
from jwt.exceptions import InvalidTokenError
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.models.user import pwd_context

ADMIN_COOKIE = "admin_session"
ADMIN_TOKEN_TYPE = "admin"
MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)

# Verified when the e-mail is wrong, so a bad e-mail costs as much time as a bad password.
_dummy_hash: Optional[str] = None

# Failed login timestamps. Global rather than per-IP: one admin, and the app sits behind a proxy.
_failures: List[datetime] = []


def admin_enabled() -> bool:
    """
    The panel exists only when an e-mail and a bcrypt hash are configured.

    It also stays off while SECRET_KEY is the default published in the
    repository: with that key anyone could sign their own admin session.
    """
    if settings.secret_key == type(settings).model_fields["secret_key"].default:
        return False
    email = (settings.admin_email or "").strip()
    password_hash = settings.admin_password_hash or ""
    return bool(email) and password_hash.startswith("$2")


def _get_dummy_hash() -> str:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = pwd_context.hash("not-the-admin-password")
    return _dummy_hash


def verify_credentials(email: str, password: str) -> bool:
    """Check a login attempt against the configured admin."""
    if not admin_enabled():
        return False
    expected = settings.admin_email.strip().lower().encode()
    given = (email or "").strip().lower().encode()
    email_ok = hmac.compare_digest(expected, given)
    try:
        password_ok = pwd_context.verify(
            password or "", settings.admin_password_hash if email_ok else _get_dummy_hash()
        )
    except ValueError:
        password_ok = False
    return email_ok and password_ok


def create_admin_token() -> str:
    """
    Session token for the admin cookie.

    It carries no "sub" claim on purpose: the user API identifies callers by
    "sub", so this token can never authenticate as a user there.
    """
    payload = {
        "type": ADMIN_TOKEN_TYPE,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.admin_session_hours),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def is_admin_token(token: Optional[str]) -> bool:
    """True only for an unexpired token that was issued by create_admin_token."""
    if not token or not admin_enabled():
        return False
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"require": ["exp"]},
        )
    except InvalidTokenError:
        return False
    return payload.get("type") == ADMIN_TOKEN_TYPE and "sub" not in payload


def _recent_failures() -> List[datetime]:
    cutoff = datetime.now(timezone.utc) - FAILURE_WINDOW
    _failures[:] = [moment for moment in _failures if moment > cutoff]
    return _failures


def login_blocked() -> bool:
    """Whether logins are refused because of too many recent failures."""
    return len(_recent_failures()) >= MAX_FAILURES


def record_failure() -> None:
    _recent_failures().append(datetime.now(timezone.utc))


def reset_failures() -> None:
    _failures.clear()


class AdminLoginRequired(Exception):
    """Raised by require_admin; the app turns it into a redirect to the login page."""


def require_admin(request: Request) -> None:
    """Dependency guarding every admin page."""
    if not is_admin_token(request.cookies.get(ADMIN_COOKIE)):
        raise AdminLoginRequired()


def is_admin_path(path: str) -> bool:
    return path == "/admin" or path.startswith("/admin/")


def _is_cross_origin(method: str, headers: Headers) -> bool:
    """
    Whether a browser sent this request from another origin in a way that must be refused.

    SameSite=Strict does not stop a sibling subdomain from sending the cookie,
    so cross-origin reads and form posts are refused outright. Following a
    link to the panel from elsewhere is fine: a top-level GET navigation
    cannot hand the response to the page that started it.
    """
    fetch_site = headers.get("sec-fetch-site")
    if fetch_site is not None:
        if fetch_site in ("same-origin", "none"):
            return False
        is_link_navigation = (
            method in ("GET", "HEAD")
            and headers.get("sec-fetch-mode") == "navigate"
            and headers.get("sec-fetch-dest") == "document"
        )
        return not is_link_navigation

    # Older browsers: compare Origin with the host the request was addressed to.
    origin = headers.get("origin")
    if origin is None:
        return False
    origin_host = urlparse(origin).netloc.lower()
    # A cross-site page cannot set X-Forwarded-Host on the victim's request,
    # so honouring it (for proxies that rewrite Host) does not weaken the check.
    own_hosts = {
        value.strip().lower()
        for value in (headers.get("host"), headers.get("x-forwarded-host"))
        if value
    }
    return origin_host not in own_hosts


class AdminGuardMiddleware:
    """
    Everything that applies to every /admin request, static files included:
    the off-switch, the cross-origin refusal, and the response headers.

    Must wrap CORSMiddleware so the CORS headers it adds can be removed.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_admin_path(scope["path"]):
            await self.app(scope, receive, send)
            return

        async def send_guarded(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name in [key for key in headers.keys() if key.lower().startswith("access-control-")]:
                    del headers[name]
                headers["Cache-Control"] = "no-store"
                headers["X-Robots-Tag"] = "noindex, nofollow"
                headers["X-Frame-Options"] = "DENY"
            await send(message)

        if not admin_enabled():
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send_guarded)
            return
        if _is_cross_origin(scope["method"], Headers(scope=scope)):
            await PlainTextResponse("Forbidden", status_code=403)(scope, receive, send_guarded)
            return

        await self.app(scope, receive, send_guarded)
