"""
Celery Application Configuration for Evaluation Bien Service
"""
import os
from celery import Celery

# RabbitMQ Broker URL
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", "5672")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")

BROKER_URL = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}:{RABBITMQ_PORT}//"

# Redis Result Backend URL
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_DB = os.getenv("REDIS_DB", "1")  # Different DB from credit service

RESULT_BACKEND = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Create Celery app
celery_app = Celery(
    "evaluation_bien_service",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=['tasks']
)

# Celery Configuration
celery_app.conf.update(
    # Task execution settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Retry configuration with exponential backoff
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,  # 60 seconds initial delay
    task_max_retries=5,
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_persistent=True,
    
    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time for fairness
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    
    # Visibility timeout
    broker_transport_options={
        'visibility_timeout': 3600,  # 1 hour
        'max_retries': 5,
        'interval_start': 0,
        'interval_step': 0.2,
        'interval_max': 0.5,
    },
    
    # Task routing
    task_routes={
        'tasks.evaluer_bien_task': {
            'queue': 'property_evaluation_queue',
            'routing_key': 'property.evaluation',
        }
    },
    
    # Monitoring
    task_track_started=True,
    task_send_sent_event=True,
)

if __name__ == '__main__':
    celery_app.start()
