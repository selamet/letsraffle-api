"""
Celery Tasks for Email Operations
"""

import logging
from typing import Dict, Any
from app.celery_app import app
from app.services.email_service import EmailService
from app.models.draw import Language

logger = logging.getLogger(__name__)


@app.task(bind=True, name='send_password_reset_email_task')
def send_password_reset_email_task(
    self,
    email: str,
    token: str,
    language: str = Language.TR.value
) -> Dict[str, Any]:
    """
    Send password reset email asynchronously
    
    Args:
        email: User's email address
        token: Reset token
        language: Language code (default: tr)
        
    Returns:
        Dict with status and message
    """
    logger.info(f"Starting send_password_reset_email_task for {email}")
    
    try:
        email_service = EmailService()
        success = email_service.send_password_reset_email(email, token, language)
        
        if success:
            logger.info(f"Password reset email sent successfully to {email}")
            return {"status": "success", "message": f"Email sent to {email}"}
        else:
            logger.error(f"Failed to send password reset email to {email}")
            return {"status": "error", "message": f"Failed to send email to {email}"}
            
    except Exception as e:
        logger.error(f"Unexpected error in send_password_reset_email_task: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def _run_draw_email(action) -> Dict[str, Any]:
    """Run a draw e-mail action with its own session; e-mail problems never break draw flows."""
    from app.models.database import SessionLocal

    db = SessionLocal()
    try:
        return {"status": "success", "sent": action(db)}
    except Exception as exc:
        logger.error(f"Draw e-mail task failed: {exc}", exc_info=True)
        return {"status": "error", "message": str(exc)}
    finally:
        db.close()


@app.task(name='send_join_confirmation_email_task')
def send_join_confirmation_email_task(participant_id: int) -> Dict[str, Any]:
    from app.services.draw_email_service import send_join_confirmation
    return _run_draw_email(lambda db: send_join_confirmation(db, participant_id))


@app.task(name='send_draw_created_email_task')
def send_draw_created_email_task(draw_id: int) -> Dict[str, Any]:
    from app.services.draw_email_service import send_draw_created
    return _run_draw_email(lambda db: send_draw_created(db, draw_id))


@app.task(name='send_draw_reminder_emails_task')
def send_draw_reminder_emails_task() -> Dict[str, Any]:
    from app.services.draw_email_service import send_due_reminder_emails
    return _run_draw_email(lambda db: send_due_reminder_emails(db))
