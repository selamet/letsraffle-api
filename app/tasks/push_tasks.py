"""
Celery tasks for push notifications
"""

import logging
from typing import Any, Dict

from app.celery_app import app
from app.models.database import SessionLocal
from app.services.push_service import PushService

logger = logging.getLogger(__name__)


def _run(action) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        service = PushService(db)
        if not service.enabled:
            return {"status": "skipped", "reason": "apns_not_configured"}
        return {"status": "success", "sent": action(service)}
    except Exception as exc:  # Push must never break draw flows
        logger.error(f"Push task failed: {exc}", exc_info=True)
        return {"status": "error", "message": str(exc)}
    finally:
        db.close()


def enqueue(task, *args) -> None:
    """Queue a push task without letting broker errors break the calling flow."""
    try:
        task.delay(*args)
    except Exception as exc:
        logger.warning(f"Could not enqueue {task.name}: {exc}")


@app.task(name="send_match_revealed_push_task")
def send_match_revealed_push_task(draw_id: int) -> Dict[str, Any]:
    return _run(lambda service: service.notify_match_revealed(draw_id))


@app.task(name="send_participant_joined_push_task")
def send_participant_joined_push_task(draw_id: int, participant_name: str) -> Dict[str, Any]:
    return _run(lambda service: service.notify_participant_joined(draw_id, participant_name))


@app.task(name="send_draw_reminders_task")
def send_draw_reminders_task() -> Dict[str, Any]:
    return _run(lambda service: service.send_due_reminders())


@app.task(name="send_join_digests_task")
def send_join_digests_task() -> Dict[str, Any]:
    return _run(lambda service: service.send_join_digests())


@app.task(name="send_draw_not_run_push_task")
def send_draw_not_run_push_task(draw_id: int, participant_count: int) -> Dict[str, Any]:
    return _run(lambda service: service.notify_draw_not_run(draw_id, participant_count))
