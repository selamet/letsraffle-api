"""
Celery Tasks for Draw Operations

Handles asynchronous draw processing.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.celery_app import app
from app.models.database import SessionLocal
from app.services.draw_service import DrawService
from app.services.email_service import EmailService
from app.models.draw import Draw, DrawStatus, Language, Participant
from app.core.exceptions import (
    DrawServiceException,
    InsufficientParticipantsError,
    DrawAlreadyCompletedError,
    DrawNotFoundError
)

logger = logging.getLogger(__name__)


@app.task(bind=True, name='execute_scheduled_draw_task')
def execute_scheduled_draw_task(self) -> Dict[str, Any]:
    """
    Execute scheduled draws (runs periodically via Celery Beat every hour).

    Finds draws that have a scheduled draw_date that has arrived and are ready to be executed.
    Processes each draw asynchronously. Log messages are based on draw language (TR/EN).

    Note: draw_date is already stored in UTC in the database, so we compare directly with UTC.

    Returns:
        Dict with status, message, and execution details
    """
    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc)

        scheduled_draws = db.query(Draw).filter(
            and_(
                Draw.draw_date.isnot(None),
                Draw.draw_date <= now,
                Draw.status.in_([DrawStatus.ACTIVE.value, DrawStatus.IN_PROGRESS.value])
            )
        ).all()

        if not scheduled_draws:
            db.close()
            return {
                "status": "success",
                "message": "No scheduled draws to execute",
                "draws_processed": 0
            }

        processed_draws = []
        skipped_draws = []

        for draw in scheduled_draws:
            participant_count = db.query(Participant).filter(
                Participant.draw_id == draw.id
            ).count()

            if participant_count < 3:
                skipped_draws.append({
                    "draw_id": draw.id,
                    "reason": "insufficient_participants",
                    "participant_count": participant_count
                })
                continue

            draw.status = DrawStatus.IN_PROGRESS.value
            db.commit()

            process_draw.delay(draw.id)

            processed_draws.append({
                "draw_id": draw.id,
                "draw_date": draw.draw_date.isoformat() if draw.draw_date else None,
                "language": draw.language
            })

        logger.info(
            f"execute_scheduled_draw_task: time={now.isoformat()}, "
            f"processed={len(processed_draws)}, "
            f"skipped={len(skipped_draws)}, "
            f"draw_ids={[d['draw_id'] for d in processed_draws]}"
        )

        return {
            "status": "success",
            "message": f"Processed {len(processed_draws)} draws, skipped {len(skipped_draws)}",
            "draws_processed": len(processed_draws),
            "draws_skipped": len(skipped_draws),
            "processed_draws": processed_draws,
            "skipped_draws": skipped_draws
        }

    except Exception as e:
        logger.error(f'Unexpected error in execute_scheduled_draw_task: {str(e)}', exc_info=True)
        return {
            "status": "error",
            "message": f"Error executing scheduled draws: {str(e)}",
            "draws_processed": 0
        }
    finally:
        db.close()


@app.task(bind=True, name='process_draw')
def process_draw(self, draw_id: int) -> Dict[str, Any]:
    """
    Process manual draw execution
    
    Steps:
    1. Execute draw algorithm
    2. Create DrawResult records
    3. Send emails to participants
    4. Update draw status to COMPLETED
    
    Args:
        draw_id: ID of the draw to process
        
    Returns:
        Dict with status, message, and execution details
    """
    logger.info(f'process_draw started for draw_id={draw_id}')
    
    db = SessionLocal()
    
    try:
        service = DrawService(db)
        results = service.execute_draw(draw_id)
        db.commit()
        
        logger.info(f'Draw processed successfully: draw_id={draw_id}, matches_created={len(results)}')
        
        email_summary = _send_draw_result_emails(db, draw_id, results)
        
        return {
            "status": "success",
            "message": f"Draw {draw_id} processed successfully",
            "matches_created": len(results),
            **email_summary
        }
        
    except DrawNotFoundError as e:
        return _handle_error(db, draw_id, "not_found", str(e), logger.error)
        
    except InsufficientParticipantsError as e:
        return _handle_error(db, draw_id, "insufficient_participants", str(e), logger.error)
        
    except DrawAlreadyCompletedError as e:
        return _handle_error(db, draw_id, "already_completed", str(e), logger.warning)
        
    except DrawServiceException as e:
        return _handle_error(db, draw_id, "service_error", str(e), logger.error)
        
    except Exception as e:
        logger.error(f'Unexpected error in draw task: draw_id={draw_id}, error={str(e)}', exc_info=True)
        return _handle_error(db, draw_id, "unexpected", f"Unexpected error: {str(e)}", logger.error)
        
    finally:
        db.close()


def _send_draw_result_emails(
    db: Session,
    draw_id: int,
    draw_results: list
) -> Dict[str, Any]:
    """
    Send emails to all participants with their draw results
    
    Args:
        db: Database session
        draw_id: ID of the draw
        draw_results: List of DrawResult objects
        
    Returns:
        Dictionary with email sending summary
    """
    try:
        draw = db.query(Draw).filter(Draw.id == draw_id).first()

        if not draw:
            logger.error(f'Draw not found after execution: draw_id={draw_id}')
            return {"email_error": "Draw not found after execution"}
        
        participants_dict = {p.id: p for p in draw.participants}
        email_service = EmailService()
        email_results = email_service.send_draw_results_to_all_participants(
            draw=draw,
            draw_results=draw_results,
            participants_dict=participants_dict
        )
        
        successful_emails = sum(1 for success in email_results.values() if success)
        return {
            "emails_sent": successful_emails,
            "emails_total": len(email_results)
        }
        
    except Exception as email_error:
        logger.error(
            f'Failed to send emails for draw {draw_id}: {str(email_error)}',
            exc_info=True
        )
        return {"email_error": str(email_error)}


def _handle_error(
    db: Session,
    draw_id: int,
    error_type: str,
    message: str,
    log_func
) -> Dict[str, str]:
    """Handle error and return error response"""
    log_func(f'{error_type}: draw_id={draw_id}, error={message}')
    db.rollback()
    return {
        "status": "error",
        "error_type": error_type,
        "message": message
    }
