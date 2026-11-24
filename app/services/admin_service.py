"""
Read-only queries behind the admin panel.

Nothing in this module writes to the database. Lists never issue per-row
queries: counts come from grouped subqueries and matches from joins.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, Generic, List, Optional, TypeVar, Union

from sqlalchemy import func, or_
from sqlalchemy.orm import Query, Session, aliased

from app.models import Device, Draw, DrawResult, EmailUnsubscribe, Participant, User
from app.core.client_source import ClientSource
from app.models.draw import DrawStatus, DrawType, Language

PAGE_SIZE = 50
MAX_PAGE = 100_000
# Largest value a PostgreSQL integer primary key can hold.
MAX_ID = 2_147_483_647
OVERVIEW_DAYS = 30
LATEST_DRAWS = 10
MIN_PEOPLE_QUERY = 2
# ?source= value that lists draws created before the source was recorded.
SOURCE_NOT_RECORDED = "none"

# Turkey has been on a fixed UTC+3 offset since 2016.
ISTANBUL = timezone(timedelta(hours=3))

T = TypeVar("T")


@dataclass
class Page(Generic[T]):
    items: List[T]
    page: int
    total: int
    has_prev: bool
    has_next: bool


@dataclass
class DrawRow:
    id: int
    created_at: datetime
    creator_id: Optional[int]
    creator_email: Optional[str]
    draw_type: str
    status: str
    draw_date: Optional[datetime]
    participant_count: int
    language: str
    source: Optional[str]


@dataclass
class DayCount:
    day: date  # Istanbul calendar day
    draws: int
    participants: int


@dataclass
class Overview:
    users: int
    draws_total: int
    draws_by_status: Dict[str, int]
    draws_by_source: Dict[Optional[str], int]  # None = created before the source was recorded
    participants: int
    devices: int
    unsubscribes: int
    daily: List[DayCount]  # OVERVIEW_DAYS entries, oldest first, ending today
    latest_draws: List[DrawRow]


@dataclass
class MatchRow:
    giver: Participant
    receiver: Participant


@dataclass
class DrawDetail:
    draw: Draw
    creator_email: Optional[str]
    participants: List[Participant]
    matches: List[MatchRow]


@dataclass
class UserRow:
    id: int
    email: str
    created_at: datetime
    has_password: bool
    has_apple: bool
    has_google: bool
    draw_count: int
    device_count: int
    source: Optional[str]


@dataclass
class ParticipationRow:
    participant: Participant
    draw_id: int
    draw_status: str
    draw_created_at: datetime
    drew: Optional[Participant]  # who this participant gives to
    drawn_by: Optional[Participant]  # who gives to this participant


@dataclass
class UserDetail:
    user: User
    draws: List[DrawRow]
    participations: List[ParticipationRow]


# --- Helpers ----------------------------------------------------------------

def clamp_page(raw: Union[str, int, None]) -> int:
    """Turn whatever arrived in ?page= into a valid page number."""
    try:
        page = int(raw)
    except (TypeError, ValueError):
        return 1
    return min(max(page, 1), MAX_PAGE)


def parse_id(raw: Union[str, int, None]) -> Optional[int]:
    """Turn a path segment into a row id, or None when it cannot be one."""
    text = str(raw)
    if not text.isascii() or not text.isdecimal():
        return None
    value = int(text) if len(text) <= 10 else MAX_ID + 1
    return value if 1 <= value <= MAX_ID else None


def clean_query(text: Optional[str]) -> str:
    """Search text as typed, minus NUL bytes, which PostgreSQL refuses in a string."""
    return (text or "").replace("\x00", "").strip()


def _contains(column, text: str):
    """Case-insensitive substring match that treats % and _ in the text literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def _enum_value(enum_cls, raw: Optional[str]) -> Optional[str]:
    """The raw value if it is a member of the enum, otherwise None (filter ignored)."""
    if raw and raw in {member.value for member in enum_cls}:
        return raw
    return None


def _paginate(query: Query, page: int, build) -> Page:
    page = clamp_page(page)
    total = query.order_by(None).count()
    rows = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()
    return Page(
        items=[build(row) for row in rows],
        page=page,
        total=total,
        has_prev=page > 1,
        has_next=page * PAGE_SIZE < total,
    )


def _draw_rows_query(db: Session) -> Query:
    counts = (
        db.query(Participant.draw_id.label("draw_id"), func.count(Participant.id).label("n"))
        .group_by(Participant.draw_id)
        .subquery()
    )
    return (
        db.query(Draw, User.email, func.coalesce(counts.c.n, 0))
        .outerjoin(User, User.id == Draw.creator_id)
        .outerjoin(counts, counts.c.draw_id == Draw.id)
        .order_by(Draw.created_at.desc(), Draw.id.desc())
    )


def _draw_row(row) -> DrawRow:
    draw, creator_email, participant_count = row
    return DrawRow(
        id=draw.id,
        created_at=draw.created_at,
        creator_id=draw.creator_id,
        creator_email=creator_email,
        draw_type=draw.draw_type,
        status=draw.status,
        draw_date=draw.draw_date,
        participant_count=participant_count,
        language=draw.language,
        source=draw.source,
    )


def _participations_query(db: Session) -> Query:
    """Participants with their draw, who they drew and who drew them, in one query."""
    given = aliased(DrawResult)
    received = aliased(DrawResult)
    drew = aliased(Participant)
    drawn_by = aliased(Participant)
    return (
        db.query(Participant, Draw, drew, drawn_by)
        .join(Draw, Draw.id == Participant.draw_id)
        .outerjoin(given, given.giver_participant_id == Participant.id)
        .outerjoin(drew, drew.id == given.receiver_participant_id)
        .outerjoin(received, received.receiver_participant_id == Participant.id)
        .outerjoin(drawn_by, drawn_by.id == received.giver_participant_id)
        .order_by(Participant.created_at.desc(), Participant.id.desc())
    )


def _participation_row(row) -> ParticipationRow:
    participant, draw, drew, drawn_by = row
    return ParticipationRow(
        participant=participant,
        draw_id=draw.id,
        draw_status=draw.status,
        draw_created_at=draw.created_at,
        drew=drew,
        drawn_by=drawn_by,
    )


def _istanbul_day(moment: datetime) -> date:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(ISTANBUL).date()


# --- Queries ----------------------------------------------------------------

def get_overview(db: Session, now: Optional[datetime] = None) -> Overview:
    now = now or datetime.now(timezone.utc)
    today = _istanbul_day(now)
    first_day = today - timedelta(days=OVERVIEW_DAYS - 1)
    since = datetime.combine(first_day, time.min, tzinfo=ISTANBUL).astimezone(timezone.utc)

    days = {first_day + timedelta(days=offset): DayCount(first_day + timedelta(days=offset), 0, 0) for offset in range(OVERVIEW_DAYS)}
    # Bucketed in Python so the Istanbul day boundary behaves the same on every database.
    for (created_at,) in db.query(Draw.created_at).filter(Draw.created_at >= since):
        bucket = days.get(_istanbul_day(created_at))
        if bucket:
            bucket.draws += 1
    for (created_at,) in db.query(Participant.created_at).filter(Participant.created_at >= since):
        bucket = days.get(_istanbul_day(created_at))
        if bucket:
            bucket.participants += 1

    by_status = dict(db.query(Draw.status, func.count(Draw.id)).group_by(Draw.status).all())
    by_source = dict(db.query(Draw.source, func.count(Draw.id)).group_by(Draw.source).all())

    return Overview(
        users=db.query(func.count(User.id)).scalar() or 0,
        draws_total=sum(by_status.values()),
        draws_by_status=by_status,
        draws_by_source=by_source,
        participants=db.query(func.count(Participant.id)).scalar() or 0,
        devices=db.query(func.count(Device.id)).scalar() or 0,
        unsubscribes=db.query(func.count(EmailUnsubscribe.id)).scalar() or 0,
        daily=[days[day] for day in sorted(days)],
        latest_draws=[_draw_row(row) for row in _draw_rows_query(db).limit(LATEST_DRAWS).all()],
    )


def list_draws(
    db: Session,
    *,
    status: Optional[str] = None,
    draw_type: Optional[str] = None,
    language: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    page: Union[str, int, None] = 1,
) -> Page[DrawRow]:
    query = _draw_rows_query(db)

    status = _enum_value(DrawStatus, status)
    draw_type = _enum_value(DrawType, draw_type)
    language = _enum_value(Language, language)
    if status:
        query = query.filter(Draw.status == status)
    if draw_type:
        query = query.filter(Draw.draw_type == draw_type)
    if language:
        query = query.filter(Draw.language == language)
    if source == SOURCE_NOT_RECORDED:
        query = query.filter(Draw.source.is_(None))
    else:
        source = _enum_value(ClientSource, source)
        if source:
            query = query.filter(Draw.source == source)

    q = clean_query(q)
    if q:
        conditions = [_contains(User.email, q), _contains(Draw.invite_code, q)]
        draw_id = parse_id(q)
        if draw_id:
            conditions.append(Draw.id == draw_id)
        query = query.filter(or_(*conditions))

    return _paginate(query, page, _draw_row)


def get_draw(db: Session, draw_id: Union[str, int]) -> Optional[DrawDetail]:
    draw_id = parse_id(draw_id)
    if draw_id is None:
        return None
    found = db.query(Draw, User.email).outerjoin(User, User.id == Draw.creator_id).filter(Draw.id == draw_id).first()
    if not found:
        return None
    draw, creator_email = found

    participants = (
        db.query(Participant)
        .filter(Participant.draw_id == draw_id)
        .order_by(Participant.created_at.asc(), Participant.id.asc())
        .all()
    )
    giver = aliased(Participant)
    receiver = aliased(Participant)
    matches = (
        db.query(giver, receiver)
        .select_from(DrawResult)
        .join(giver, giver.id == DrawResult.giver_participant_id)
        .join(receiver, receiver.id == DrawResult.receiver_participant_id)
        .filter(DrawResult.draw_id == draw_id)
        .order_by(giver.first_name, giver.last_name, giver.id)
        .all()
    )
    return DrawDetail(
        draw=draw,
        creator_email=creator_email,
        participants=participants,
        matches=[MatchRow(giver=g, receiver=r) for g, r in matches],
    )


def list_users(db: Session, *, q: Optional[str] = None, page: Union[str, int, None] = 1) -> Page[UserRow]:
    draw_counts = (
        db.query(Draw.creator_id.label("user_id"), func.count(Draw.id).label("n"))
        .filter(Draw.creator_id.isnot(None))
        .group_by(Draw.creator_id)
        .subquery()
    )
    device_counts = (
        db.query(Device.user_id.label("user_id"), func.count(Device.id).label("n"))
        .filter(Device.user_id.isnot(None))
        .group_by(Device.user_id)
        .subquery()
    )
    query = (
        db.query(User, func.coalesce(draw_counts.c.n, 0), func.coalesce(device_counts.c.n, 0))
        .outerjoin(draw_counts, draw_counts.c.user_id == User.id)
        .outerjoin(device_counts, device_counts.c.user_id == User.id)
        .order_by(User.created_at.desc(), User.id.desc())
    )
    q = clean_query(q)
    if q:
        query = query.filter(_contains(User.email, q))

    def build(row) -> UserRow:
        user, draw_count, device_count = row
        return UserRow(
            id=user.id,
            email=user.email,
            created_at=user.created_at,
            has_password=bool(user.password),
            has_apple=user.has_apple,
            has_google=user.has_google,
            draw_count=draw_count,
            device_count=device_count,
            source=user.source,
        )

    return _paginate(query, page, build)


def get_user(db: Session, user_id: Union[str, int]) -> Optional[UserDetail]:
    user_id = parse_id(user_id)
    if user_id is None:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    draws = _draw_rows_query(db).filter(Draw.creator_id == user_id).all()
    participations = (
        _participations_query(db).filter(func.lower(Participant.email) == user.email.lower()).all()
    )
    return UserDetail(
        user=user,
        draws=[_draw_row(row) for row in draws],
        participations=[_participation_row(row) for row in participations],
    )


def search_people(db: Session, q: str, page: Union[str, int, None] = 1) -> Page[ParticipationRow]:
    q = clean_query(q)
    if len(q) < MIN_PEOPLE_QUERY:
        return Page(items=[], page=1, total=0, has_prev=False, has_next=False)

    full_name = Participant.first_name + " " + Participant.last_name
    query = _participations_query(db).filter(
        or_(
            _contains(Participant.email, q),
            _contains(Participant.first_name, q),
            _contains(Participant.last_name, q),
            _contains(full_name, q),
        )
    )
    return _paginate(query, page, _participation_row)
