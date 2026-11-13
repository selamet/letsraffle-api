"""
Marketing e-mail bookkeeping: who opted out and who already received a campaign
"""

from sqlalchemy import Column, Integer, String, UniqueConstraint
from app.models.base import BaseModel


class EmailUnsubscribe(BaseModel):
    """An address that asked not to receive announcement e-mails. Stored lower-cased."""

    __tablename__ = "email_unsubscribes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)

    def __repr__(self):
        return f"<EmailUnsubscribe(email={self.email})>"


class CampaignEmail(BaseModel):
    """One row per (campaign, address) that was sent, so a campaign can be resumed without duplicates."""

    __tablename__ = "campaign_emails"
    __table_args__ = (
        UniqueConstraint("campaign", "email", name="uq_campaign_email"),
    )

    id = Column(Integer, primary_key=True, index=True)
    campaign = Column(String(64), nullable=False, index=True)
    email = Column(String(255), nullable=False)

    def __repr__(self):
        return f"<CampaignEmail(campaign={self.campaign}, email={self.email})>"
