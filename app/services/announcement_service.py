"""
Announcement campaigns: who should receive one.

Recipients are registered users (optionally also everyone who joined a draw). Addresses that
opted out, or that already received the campaign, are left out.
"""

from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models.draw import Draw, Language, Participant
from app.models.email import CampaignEmail, EmailUnsubscribe
from app.models.user import User

AUDIENCE_USERS = "users"
AUDIENCE_ALL = "all"


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _looks_deliverable(email: str) -> bool:
    local, _, domain = email.partition("@")
    return bool(local) and "." in domain and " " not in email


def collect_recipients(db: Session, campaign: str, audience: str = AUDIENCE_USERS) -> List[Tuple[str, str]]:
    """
    Return (email, language) pairs for a campaign, sorted by address.

    The language is the one of the most recent draw the address created or joined; Turkish otherwise.
    """
    # Most recent draw language per address, from draws they joined and draws they created.
    languages: Dict[str, str] = {}
    joined = (
        db.query(Participant.email, Draw.language)
        .join(Draw, Participant.draw_id == Draw.id)
        .order_by(Draw.created_at.asc(), Draw.id.asc())
        .all()
    )
    for email, language in joined:
        languages[normalize_email(email)] = (language or Language.TR.value).upper()
    created = (
        db.query(User.email, Draw.language)
        .join(Draw, Draw.creator_id == User.id)
        .order_by(Draw.created_at.asc(), Draw.id.asc())
        .all()
    )
    for email, language in created:
        languages[normalize_email(email)] = (language or Language.TR.value).upper()

    addresses = {normalize_email(email) for (email,) in db.query(User.email).all()}
    if audience == AUDIENCE_ALL:
        addresses |= {normalize_email(email) for (email,) in db.query(Participant.email).distinct().all()}

    opted_out = {normalize_email(email) for (email,) in db.query(EmailUnsubscribe.email).all()}
    already_sent = {
        normalize_email(email)
        for (email,) in db.query(CampaignEmail.email).filter(CampaignEmail.campaign == campaign).all()
    }

    recipients = [
        (email, languages.get(email, Language.TR.value))
        for email in addresses
        if _looks_deliverable(email) and email not in opted_out and email not in already_sent
    ]
    return sorted(recipients)


def mark_sent(db: Session, campaign: str, email: str) -> None:
    db.add(CampaignEmail(campaign=campaign, email=normalize_email(email)))
    db.commit()
