"""
Event Consumer for Service Demandes
Consumes events from other services to update loan request state in database

CRITICAL FIXES APPLIED:
1. Atomic idempotency using INSERT ON CONFLICT
2. Single transaction per event (no multiple commits)
"""
import logging
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import sys
sys.path.append('/app')

from shared.events import Event
from shared.rabbitmq import RabbitMQClient, EventConsumer
from database import AsyncSessionLocal
from repository import DemandeRepository, IdempotencyRepository

logger = logging.getLogger(__name__)


async def handle_credit_evaluated(event: Event):
    """
    Handler pour l'événement credit.evaluated
    Met à jour la demande avec les résultats de l'évaluation crédit
    
    ATOMICITY GUARANTEE:
    - Uses try_mark_as_processed() for atomic idempotency check
    - Single database transaction for all operations
    - No crash window between business update and idempotency mark
    """
    demande_id = event.demande_id
    data = event.data
    correlation_id = event.correlation_id
    
    logger.info(f"📨 [Consumer] Traitement credit.evaluated: {demande_id}")
    
    async with AsyncSessionLocal() as session:
        # ✅ BEGIN EXPLICIT TRANSACTION
        async with session.begin():
            try:
                # ✅ ATOMIC IDEMPOTENCY CHECK
                # This INSERT ON CONFLICT operation is atomic - only ONE worker will succeed
                should_process = await IdempotencyRepository.try_mark_as_processed(
                    session,
                    correlation_id,
                    "credit.evaluated",
                    demande_id,
                    "service-demandes"
                )
                
                if not should_process:
                    # Another worker already processed this message
                    logger.info(f"⚠️ Message déjà traité par un autre worker, ignoré: {correlation_id}")
                    # Transaction will rollback automatically (no changes made)
                    return
                
                # ✅ UPDATE BUSINESS DATA (within same transaction)
                # This worker won the race, safe to process
                await DemandeRepository.update_credit_evaluation(
                    session,
                    demande_id,
                    score_credit=data.get("score_credit"),
                    antecedents_positifs=data.get("antecedents_positifs"),
                    dettes_existantes=data.get("dettes_existantes"),
                    ratio_dette_revenu=data.get("ratio_dette_revenu")
                )
                
                # ✅ SINGLE COMMIT AT END OF CONTEXT
                # Both idempotency mark AND business update commit together
                # No crash window between operations
                
            except Exception as e:
                logger.error(f"✗ [Consumer] Erreur lors du traitement: {e}")
                # Transaction will rollback automatically on exception
                raise
        
        # If we reach here, transaction committed successfully
        logger.info(f"✓ [Consumer] Évaluation crédit enregistrée atomiquement pour {demande_id}")


async def handle_bien_evaluated(event: Event):
    """
    Handler pour l'événement bien.evaluated
    Met à jour la demande avec les résultats de l'évaluation du bien
    
    ATOMICITY GUARANTEE:
    - Uses try_mark_as_processed() for atomic idempotency check
    - Single database transaction for all operations
    - No crash window between business update and idempotency mark
    """
    demande_id = event.demande_id
    data = event.data
    correlation_id = event.correlation_id
    
    logger.info(f"📨 [Consumer] Traitement bien.evaluated: {demande_id}")
    
    async with AsyncSessionLocal() as session:
        # ✅ BEGIN EXPLICIT TRANSACTION
        async with session.begin():
            try:
                # ✅ ATOMIC IDEMPOTENCY CHECK
                should_process = await IdempotencyRepository.try_mark_as_processed(
                    session,
                    correlation_id,
                    "bien.evaluated",
                    demande_id,
                    "service-demandes"
                )
                
                if not should_process:
                    logger.info(f"⚠️ Message déjà traité par un autre worker, ignoré: {correlation_id}")
                    return
                
                # ✅ UPDATE BUSINESS DATA (within same transaction)
                await DemandeRepository.update_property_evaluation(
                    session,
                    demande_id,
                    valeur_bien=data.get("valeur_estimee"),
                    valeur_cadastrale=data.get("valeur_cadastrale"),
                    etat_bien=data.get("etat_bien"),
                    zone_geographique=data.get("zone_geographique"),
                    ratio_pret_valeur=data.get("ratio_pret_valeur")
                )
                
                # ✅ SINGLE COMMIT AT END OF CONTEXT
                
            except Exception as e:
                logger.error(f"✗ [Consumer] Erreur lors du traitement: {e}")
                raise
        
        logger.info(f"✓ [Consumer] Évaluation bien enregistrée atomiquement pour {demande_id}")


async def handle_decision_made(event: Event):
    """
    Handler pour l'événement decision.made
    Met à jour la demande avec la décision finale
    
    ATOMICITY GUARANTEE:
    - Uses try_mark_as_processed() for atomic idempotency check
    - Single database transaction for all operations
    - No crash window between business update and idempotency mark
    """
    demande_id = event.demande_id
    data = event.data
    correlation_id = event.correlation_id
    
    logger.info(f"📨 [Consumer] Traitement decision.made: {demande_id}")
    
    async with AsyncSessionLocal() as session:
        # ✅ BEGIN EXPLICIT TRANSACTION
        async with session.begin():
            try:
                # ✅ ATOMIC IDEMPOTENCY CHECK
                should_process = await IdempotencyRepository.try_mark_as_processed(
                    session,
                    correlation_id,
                    "decision.made",
                    demande_id,
                    "service-demandes"
                )
                
                if not should_process:
                    logger.info(f"⚠️ Message déjà traité par un autre worker, ignoré: {correlation_id}")
                    return
                
                # Convert decision string to Decision enum
                from shared.models import Decision
                decision_str = data.get("decision")
                decision = Decision(decision_str) if decision_str else None
                
                # ✅ UPDATE BUSINESS DATA (within same transaction)
                await DemandeRepository.update_decision(
                    session,
                    demande_id,
                    decision=decision,
                    raison=data.get("raison", ""),
                    score_global=data.get("score_global", 0.0),
                    taux_interet=data.get("taux_interet_propose"),
                    conditions=data.get("conditions_supplementaires")
                )
                
                # ✅ SINGLE COMMIT AT END OF CONTEXT
                
            except Exception as e:
                logger.error(f"✗ [Consumer] Erreur lors du traitement: {e}")
                raise
        
        logger.info(f"✓ [Consumer] Décision enregistrée atomiquement pour {demande_id}: {decision}")


async def handle_compensation_triggered(event: Event):
    """
    Handler pour l'événement compensation.triggered
    Orchestre la compensation des étapes précédentes
    """
    demande_id = event.demande_id
    etape_echec = event.data.get("etape_echec")
    correlation_id = event.correlation_id
    
    logger.warning(f"⚠️ [Compensation] Déclenchée pour {demande_id} - Échec: {etape_echec}")
    
    async with AsyncSessionLocal() as session:
        async with session.begin():
            try:
                # Vérifier idempotence
                should_process = await IdempotencyRepository.try_mark_as_processed(
                    session,
                    correlation_id,
                    "compensation.triggered",
                    demande_id,
                    "service-demandes"
                )
                
                if not should_process:
                    logger.info(f"⚠️ Compensation déjà traitée: {correlation_id}")
                    return
                
                # Mettre à jour le statut de la demande
                from shared.models import StatutDemande
                await DemandeRepository.update_status(
                    session,
                    demande_id,
                    StatutDemande.REJECTED  # Utiliser REJECTED comme statut d'annulation
                )
                
                # Enregistrer la raison de l'échec
                from shared.models import Decision
                await DemandeRepository.update_decision(
                    session,
                    demande_id,
                    decision=Decision.REJECTED,
                    raison=f"Compensation déclenchée - {etape_echec} a échoué: {event.data.get('raison', 'Unknown')}",
                    score_global=0.0
                )
                
                logger.info(f"✓ [Compensation] Demande {demande_id} marquée comme REJECTED (compensée)")
                
            except Exception as e:
                logger.error(f"✗ [Compensation] Erreur: {e}")
                raise


async def start_consumer(rabbitmq_client: RabbitMQClient):
    """
    Démarre le consumer d'événements pour service-demandes
    
    Args:
        rabbitmq_client: Client RabbitMQ connecté
    """
    logger.info("🚀 Démarrage du consumer d'événements pour service-demandes...")
    
    event_consumer = EventConsumer(rabbitmq_client, "service_demandes_update_queue")
    
    # Enregistrer les handlers
    event_consumer.register_handler("credit.evaluated", handle_credit_evaluated)
    event_consumer.register_handler("bien.evaluated", handle_bien_evaluated)
    event_consumer.register_handler("decision.made", handle_decision_made)
    event_consumer.register_handler("compensation.triggered", handle_compensation_triggered)  # ✅ NOUVEAU
    
    # Démarrer la consommation
    await event_consumer.start()
