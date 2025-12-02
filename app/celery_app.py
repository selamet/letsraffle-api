import os
from celery import Celery
from celery.schedules import crontab

ENV = os.getenv('ENV', 'development')

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'amqp://guest:guest@rabbitmq:5672//')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

app = Celery('santas_draw')

app.conf.update(
    # Broker (RabbitMQ)
    broker_url=CELERY_BROKER_URL,

    # Result backend (Redis)
    result_backend=CELERY_RESULT_BACKEND,
    result_expires=3600,

    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    worker_concurrency=4,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=500,

    # Task execution
    task_time_limit=1800,  # 30 minutes
    task_soft_time_limit=1500,  # 25 minutes
    task_acks_late=True,

    # RabbitMQ settings
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,

    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,

    # Beat schedule (periodic tasks)
    beat_schedule={
        'execute_scheduled_draw': {
            'task': 'execute_scheduled_draw_task',
            'schedule': crontab(minute=0) # Every hour at minute 0
        },
    },
)

# Explicitly import tasks to register them
app.autodiscover_tasks(['app.tasks'])

try:
    from app.tasks import draw
    from app.tasks import email_tasks
except ImportError as e:
    pass

if __name__ == '__main__':
    app.start()
