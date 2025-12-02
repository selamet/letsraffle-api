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
