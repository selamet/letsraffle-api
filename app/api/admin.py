"""
Read-only admin panel: server-rendered pages under /admin
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.models import get_db
from app.services import admin_service
from app.core.admin_auth import (
    ADMIN_COOKIE,
    create_admin_token,
    is_admin_token,
    login_blocked,
    record_failure,
    require_admin,
    reset_failures,
    verify_credentials,
)

router = APIRouter(include_in_schema=False)

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates" / "admin"))

# Turkey has been on a fixed UTC+3 offset since 2016, so no tz database is needed.
ISTANBUL = timezone(timedelta(hours=3))
MONTHS_TR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]


def istanbul(value: Optional[datetime]) -> str:
    """Format a timestamp in Istanbul time, e.g. "15 Kas 2026 14:30". Naive values are UTC."""
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(ISTANBUL)
    return f"{local.day} {MONTHS_TR[local.month - 1]} {local.year} {local:%H:%M}"


def istanbul_day(value) -> str:
    """Format a calendar day, e.g. "15 Kas"."""
    return f"{value.day} {MONTHS_TR[value.month - 1]}"


STATUS_TR = {"active": "Aktif", "in_progress": "Sürüyor", "completed": "Tamamlandı", "cancelled": "İptal"}
TYPE_TR = {"manual": "Manuel", "dynamic": "Davetli"}
# Keys are draw/user `source` values; `none` stands for rows created before the source was recorded.
SOURCE_TR = {"ios": "iOS", "web": "Web", "unknown": "Bilinmiyor", admin_service.SOURCE_NOT_RECORDED: "Kayıt yok"}

templates.env.filters["istanbul"] = istanbul
templates.env.filters["istanbul_day"] = istanbul_day
templates.env.globals.update(STATUS_TR=STATUS_TR, TYPE_TR=TYPE_TR, SOURCE_TR=SOURCE_TR)


def render(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
    return templates.TemplateResponse(request, name, context, status_code=status_code)


# --- Session ----------------------------------------------------------------

@router.get("/login")
def login_page(request: Request):
    if is_admin_token(request.cookies.get(ADMIN_COOKIE)):
        return RedirectResponse("/admin", status_code=303)
    return render(request, "login.html")


@router.post("/login")
def login(request: Request, email: str = Form(""), password: str = Form("")):
    if login_blocked():
        return render(
            request,
            "login.html",
            status_code=429,
            error="Çok fazla hatalı deneme. 15 dakika sonra tekrar dene.",
        )
    if not verify_credentials(email, password):
        record_failure()
        return render(request, "login.html", status_code=401, error="E-posta veya şifre hatalı", email=email)

    reset_failures()
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(
        ADMIN_COOKIE,
        create_admin_token(),
        max_age=settings.admin_session_hours * 3600,
        path="/admin",
        httponly=True,
        samesite="strict",
        secure=settings.admin_cookie_secure,
    )
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(ADMIN_COOKIE, path="/admin")
    return response


# --- Pages ---------------------------------------------------------------

GUARD = [Depends(require_admin)]


@router.get("", dependencies=GUARD)
def overview(request: Request, db: Session = Depends(get_db)):
    data = admin_service.get_overview(db)
    peak = max([1] + [max(day.draws, day.participants) for day in data.daily])
    return render(request, "overview.html", section="overview", o=data, peak=peak)


@router.get("/draws", dependencies=GUARD)
def draws(
    request: Request,
    status: str = "",
    type: str = "",
    language: str = "",
    source: str = "",
    q: str = "",
    page: str = "1",
    db: Session = Depends(get_db),
):
    result = admin_service.list_draws(
        db, status=status, draw_type=type, language=language, source=source, q=q, page=page
    )
    filters = {
        "status": status,
        "type": type,
        "language": language,
        "source": source if source in SOURCE_TR else "",
        "q": admin_service.clean_query(q),
    }
    return render(
        request,
        "draws.html",
        section="draws",
        result=result,
        filters=filters,
        params={key: value for key, value in filters.items() if value},
    )


@router.get("/draws/{draw_id}", dependencies=GUARD)
def draw_detail(request: Request, draw_id: str, db: Session = Depends(get_db)):
    detail = admin_service.get_draw(db, draw_id)
    if not detail:
        return render(request, "not_found.html", status_code=404, section="draws", message="Böyle bir çekiliş yok")
    return render(request, "draw_detail.html", section="draws", d=detail)


@router.get("/users", dependencies=GUARD)
def users(request: Request, q: str = "", page: str = "1", db: Session = Depends(get_db)):
    result = admin_service.list_users(db, q=q, page=page)
    q = admin_service.clean_query(q)
    return render(request, "users.html", section="users", result=result, q=q, params={"q": q} if q else {})


@router.get("/users/{user_id}", dependencies=GUARD)
def user_detail(request: Request, user_id: str, db: Session = Depends(get_db)):
    detail = admin_service.get_user(db, user_id)
    if not detail:
        return render(request, "not_found.html", status_code=404, section="users", message="Böyle bir kullanıcı yok")
    return render(request, "user_detail.html", section="users", u=detail)


@router.get("/people", dependencies=GUARD)
def people(request: Request, q: str = "", page: str = "1", db: Session = Depends(get_db)):
    q = admin_service.clean_query(q)
    result = admin_service.search_people(db, q, page=page)
    return render(
        request,
        "people.html",
        section="people",
        result=result,
        q=q,
        too_short=0 < len(q) < admin_service.MIN_PEOPLE_QUERY,
        params={"q": q},
    )
