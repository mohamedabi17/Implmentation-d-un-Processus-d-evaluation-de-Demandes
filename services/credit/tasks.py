"""
Celery Tasks for Credit Service
"""
import random
import asyncio
import logging
from celery import Task
from celery.exceptions import Retry
from celery_app import celery_app

import sys
sys.path.append('/app')

from shared.models import EvaluationCredit
from shared.rabbitmq import RabbitMQClient, EventPublisher

logger = logging.getLogger(__name__)


class CallbackTask(Task):
    """
    Base task with callback support for publishing events
    """
    _rabbitmq_client = None
    _event_publisher = None
    
    @property
    def rabbitmq_client(self):
        if self._rabbitmq_client is None:
            import os
            host = os.getenv("RABBITMQ_HOST", "localhost")
            port = int(os.getenv("RABBITMQ_PORT", "5672"))
            user = os.getenv("RABBITMQ_USER", "guest")
            password = os.getenv("RABBITMQ_PASSWORD", "guest")
            
            self._rabbitmq_client = RabbitMQClient(host, port, user, password)
            # Synchronous connection for Celery worker
            asyncio.run(self._rabbitmq_client.connect())
        return self._rabbitmq_client
    
    @property
    def event_publisher(self):
        if self._event_publisher is None:
            self._event_publisher = EventPublisher(self.rabbitmq_client)
        return self._event_publisher


@celery_app.task(
    bind=True,
    base=CallbackTask,
    name='tasks.evaluer_credit_task',
    max_retries=5,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,  # Max 10 minutes
    retry_jitter=True,
    acks_late=True
)
def evaluer_credit_task(self, demande_id: str, client_id: str, 
                        montant_demande: float, revenu_annuel: float,
                        correlation_id: str = ""):
    """
    Celery task for credit evaluation with automatic retry
    
    Args:
        demande_id: ID de la demande
        client_id: ID du client
        montant_demande: Montant demandé
        revenu_annuel: Revenu annuel
        correlation_id: ID de corrélation
        
    Returns:
        dict: Résultat de l'évaluation crédit
    """
    try:
        logger.info(f"🔍 [Celery Task] Évaluation crédit pour demande {demande_id}...")
        logger.info(f"Task ID: {self.request.id}, Retry: {self.request.retries}/{self.max_retries}")
        
        # Simulate potential transient failures
        # In production, this would be actual API calls that might fail
        if random.random() < 0.1 and self.request.retries < 2:  # 10% failure rate for demo
            logger.warning(f"⚠️ Simulating transient failure for task {self.request.id}")
            raise Exception("Transient service unavailable - will retry")
        
        # Perform credit evaluation
        # Generate realistic credit score based on income
        base_score = 550 + (revenu_annuel / 1000)
        score_credit = int(min(850, max(300, base_score + random.randint(-50, 50))))
        
        # Check credit history
        antecedents_positifs = score_credit >= 600
        
        # Simulate existing debts (0-30% of income)
        dettes_existantes = revenu_annuel * random.uniform(0, 0.3)
        
        # Calculate debt-to-income ratio
        mensualite_estimee = montant_demande / 240  # 20 year loan
        ratio_dette_revenu = ((dettes_existantes / 12 + mensualite_estimee) / (revenu_annuel / 12)) * 100
        
        evaluation = {
            "demande_id": demande_id,
            "score_credit": score_credit,
            "antecedents_positifs": antecedents_positifs,
            "dettes_existantes": round(dettes_existantes, 2),
            "ratio_dette_revenu": round(ratio_dette_revenu, 2)
        }
        
        logger.info(f"✓ [Celery Task] Crédit évalué: Score={score_credit}, Ratio={ratio_dette_revenu:.2f}%")
        
        # Publish event after successful evaluation
        try:
            asyncio.run(self.event_publisher.publish(
                event_type="credit.evaluated",
                demande_id=demande_id,
                data=evaluation,
                correlation_id=correlation_id or demande_id
            ))
            logger.info(f"📤 Event published: credit.evaluated for {demande_id}")
        except Exception as e:
            logger.error(f"✗ Failed to publish event: {e}")
            # Don't fail the task if event publishing fails
            # Store result anyway and rely on eventual consistency
        
        return evaluation
        
    except Exception as exc:
        logger.error(f"✗ [Celery Task] Error in credit evaluation: {exc}")
        
        # Check if we should retry
        if self.request.retries < self.max_retries:
            # Exponential backoff: 60s, 120s, 240s, 480s, 600s
            retry_delay = min(60 * (2 ** self.request.retries), 600)
            logger.info(f"🔄 Retrying in {retry_delay}s (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=exc, countdown=retry_delay)
        else:
            # Max retries reached, publish failure event
            logger.error(f"✗ Max retries reached for {demande_id}, publishing failure event")
            try:
                asyncio.run(self.event_publisher.publish(
                    event_type="credit.evaluation.failed",
                    demande_id=demande_id,
                    data={
                        "error": str(exc),
                        "retries": self.request.retries,
                        "task_id": self.request.id
                    },
                    correlation_id=correlation_id or demande_id
                ))
            except Exception as e:
                logger.error(f"✗ Failed to publish failure event: {e}")
            
            # Re-raise to mark task as failed
            raise
