"""
Shared helpers for tests that need valid future draw dates.
"""

from datetime import datetime, timedelta, timezone


def future_hour_iso(minute: int = 0) -> str:
    """A UTC timestamp in the future, within the current year, at the given minute."""
    now = datetime.now(timezone.utc)
    candidate = (now + timedelta(hours=2)).replace(minute=minute, second=0, microsecond=0)
    if candidate.year != now.year:
        # Last day of the year: fall back to the latest valid slot.
        candidate = now.replace(hour=23, minute=minute, second=0, microsecond=0)
    return candidate.strftime("%Y-%m-%dT%H:%M:%SZ")


def next_year_iso() -> str:
    """A timestamp in the following year (rejected by the current-year rule)."""
    return f"{datetime.now(timezone.utc).year + 1}-01-15T14:00:00Z"


def seed_admin_data(db):
    """
    Two users and two draws for admin panel tests. Returns (draw_a, draw_b).

    Draw A: created by ayse, completed, with matches Ali -> Bora -> Cem -> Ali.
    Draw B: guest draw, still active, one participant, no matches.
    """
    from app.models import Device, Draw, DrawResult, Participant, User

    ayse = User(email="ayse@example.com", password=User.hash_password("Password123!"))
    can = User(email="can@example.com", apple_sub="apple-sub-can")
    db.add_all([ayse, can])
    db.flush()
    db.add(Device(token="device-token-can", user_id=can.id))

    draw_a = Draw(creator_id=ayse.id, status="completed", draw_type="dynamic", language="EN", invite_code="ABC_1")
    draw_b = Draw(creator_id=None, status="active", draw_type="manual", language="TR")
    db.add_all([draw_a, draw_b])
    db.flush()

    ali = Participant(draw_id=draw_a.id, first_name="Ali", last_name="Kaya", email="ali@example.com")
    bora = Participant(draw_id=draw_a.id, first_name="Bora", last_name="Demir", email="bora@example.com")
    cem = Participant(draw_id=draw_a.id, first_name="Cem", last_name="Öz", email="AYSE@example.com")
    lone = Participant(draw_id=draw_b.id, first_name="Deniz", last_name="Ak", email="100%_real@example.com")
    db.add_all([ali, bora, cem, lone])
    db.flush()

    for giver, receiver in ((ali, bora), (bora, cem), (cem, ali)):
        db.add(DrawResult(draw_id=draw_a.id, giver_participant_id=giver.id, receiver_participant_id=receiver.id))
    db.commit()
    return draw_a, draw_b
