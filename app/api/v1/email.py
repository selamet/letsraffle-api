"""
Announcement e-mail opt-out.

The link in an e-mail opens a small confirmation page (GET); the opt-out itself is a POST, so
mail scanners that prefetch links never unsubscribe anyone. The same POST URL is advertised in the
List-Unsubscribe header for one-click unsubscribe (RFC 8058).
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import decode_unsubscribe_token
from app.models import get_db
from app.models.email import EmailUnsubscribe

logger = logging.getLogger(__name__)

router = APIRouter()

_templates = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent.parent.parent / "templates")),
    autoescape=select_autoescape(["html", "xml"]),
)


def _page(state: str, lang: str = "tr", token: str = "", status_code: int = 200) -> HTMLResponse:
    html = _templates.get_template("unsubscribe.html").render(
        state=state,
        lang=lang,
        token=token,
        asset_base=settings.frontend_url.rstrip("/"),
    )
    return HTMLResponse(html, status_code=status_code)


def unsubscribe_email(db: Session, email: str) -> bool:
    """Add the address to the opt-out list. Returns False when it was already there."""
    email = email.strip().lower()
    if db.query(EmailUnsubscribe.id).filter(EmailUnsubscribe.email == email).first():
        return False
    db.add(EmailUnsubscribe(email=email))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True


@router.get("/email/unsubscribe", response_class=HTMLResponse, include_in_schema=False)
async def unsubscribe_page(token: str = Query("")):
    """Confirmation page with a single button; changes nothing by itself."""
    payload = decode_unsubscribe_token(token)
    if not payload:
        return _page("invalid", status_code=400)
    return _page("confirm", lang=payload["lang"], token=token)


@router.post("/email/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(token: str = Query(""), db: Session = Depends(get_db)):
    """Opt the address in the token out of announcement e-mails. Idempotent."""
    payload = decode_unsubscribe_token(token)
    if not payload:
        return _page("invalid", status_code=400)
    if unsubscribe_email(db, payload["email"]):
        logger.info("Announcement e-mails turned off for one address")
    return _page("done", lang=payload["lang"])
