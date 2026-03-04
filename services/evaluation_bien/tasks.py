"""
Celery Tasks for Evaluation Bien Service
"""
import random
import asyncio
import logging
from celery import Task
from celery.exceptions import Retry
from celery_app import celery_app

import sys
sys.path.append('/app')

from shared.models import EvaluationBien
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
    name='tasks.evaluer_bien_task',
    max_retries=5,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,  # Max 10 minutes
    retry_jitter=True,
    acks_late=True
)
def evaluer_bien_task(self, demande_id: str, adresse_bien: str, 
                      montant_demande: float, score_credit: int = 600,
                      correlation_id: str = ""):
    """
    Celery task for property evaluation with automatic retry
    
    Args:
        demande_id: ID de la demande
        adresse_bien: Adresse du bien
        montant_demande: Montant demandé
        score_credit: Score de crédit (passé depuis l'événement précédent)
        correlation_id: ID de corrélation
        
    Returns:
        dict: Résultat de l'évaluation du bien
    """
    try:
        logger.info(f"🏠 [Celery Task] Évaluation du bien pour demande {demande_id}...")
        logger.info(f"Task ID: {self.request.id}, Retry: {self.request.retries}/{self.max_retries}")
        
        # Simulate potential transient failures
        if random.random() < 0.1 and self.request.retries < 2:  # 10% failure rate for demo
            logger.warning(f"⚠️ Simulating transient failure for task {self.request.id}")
            raise Exception("Property valuation API temporarily unavailable - will retry")
        
        # Perform property evaluation
        # Simulate valuation with variation
        variation = random.uniform(0.85, 1.25)
        valeur_estimee = montant_demande * variation
        
        # Cadastral value (slightly lower than estimate)
        valeur_cadastrale = valeur_estimee * random.uniform(0.85, 0.95)
        
        # Property condition
        etats = ["Excellent", "Bon", "Moyen", "Mauvais"]
        poids = [0.3, 0.5, 0.15, 0.05]
        etat_bien = random.choices(etats, weights=poids)[0]
        
        # Geographic zone
        zones = ["Centre-ville", "Périphérie", "Banlieue", "Rural"]
        zone_geographique = random.choice(zones)
        
        # Calculate LTV (Loan to Value)
        ratio_pret_valeur = (montant_demande / valeur_estimee) * 100
        
        evaluation = {
            "demande_id": demande_id,
            "valeur_estimee": round(valeur_estimee, 2),
            "valeur_cadastrale": round(valeur_cadastrale, 2),
            "etat_bien": etat_bien,
            "zone_geographique": zone_geographique,
            "ratio_pret_valeur": round(ratio_pret_valeur, 2),
            "score_credit": score_credit  # Pass through for next service
        }
        
        logger.info(f"✓ [Celery Task] Bien évalué: Valeur={valeur_estimee:.0f}€, LTV={ratio_pret_valeur:.2f}%")
        
        # Publish event after successful evaluation
        try:
            asyncio.run(self.event_publisher.publish(
                event_type="bien.evaluated",
                demande_id=demande_id,
                data=evaluation,
                correlation_id=correlation_id or demande_id
            ))
            logger.info(f"📤 Event published: bien.evaluated for {demande_id}")
        except Exception as e:
            logger.error(f"✗ Failed to publish event: {e}")
            # Don't fail the task if event publishing fails
        
        return evaluation
        
    except Exception as exc:
        logger.error(f"✗ [Celery Task] Error in property evaluation: {exc}")
        
        # Check if we should retry
        if self.request.retries < self.max_retries:
            # Exponential backoff
            retry_delay = min(60 * (2 ** self.request.retries), 600)
            logger.info(f"🔄 Retrying in {retry_delay}s (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=exc, countdown=retry_delay)
        else:
            # Max retries reached, publish failure event and trigger compensation
            logger.error(f"✗ Max retries reached for {demande_id}, publishing failure event")
            try:
                # Publish failure event
                asyncio.run(self.event_publisher.publish(
                    event_type="bien.evaluation.failed",
                    demande_id=demande_id,
                    data={
                        "error": str(exc),
                        "retries": self.request.retries,
                        "task_id": self.request.id
                    },
                    correlation_id=correlation_id or demande_id
                ))
                
                # Trigger compensation
                asyncio.run(self.event_publisher.publish(
                    event_type="compensation.triggered",
                    demande_id=demande_id,
                    data={
                        "etape_echec": "evaluation_bien",
                        "raison": str(exc),
                        "task_id": self.request.id
                    },
                    correlation_id=correlation_id or demande_id
                ))
            except Exception as e:
                logger.error(f"✗ Failed to publish failure events: {e}")
            
            # Re-raise to mark task as failed
            raise
