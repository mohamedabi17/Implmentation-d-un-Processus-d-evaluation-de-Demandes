"""
Service Crédit - Évaluation des antécédents de crédit
"""
import os
import random
import logging
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status

import sys
sys.path.append('/app')

from shared.models import EvaluationCredit, StatutDemande
from shared.rabbitmq import RabbitMQClient, EventPublisher, EventConsumer
from shared.events import Event
from tasks import evaluer_credit_task

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Client RabbitMQ
rabbitmq_client: RabbitMQClient | None = None
event_publisher: EventPublisher | None = None
event_consumer: EventConsumer | None = None


async def evaluer_credit(demande_id: str, client_id: str, montant_demande: float, 
                         revenu_annuel: float) -> EvaluationCredit:
    """
    Évaluer le crédit d'un client
    
    Args:
        demande_id: ID de la demande
        client_id: ID du client
        montant_demande: Montant demandé
        revenu_annuel: Revenu annuel
        
    Returns:
        Résultat de l'évaluation crédit
    """
    # Simulation d'une évaluation crédit
    # En production, ceci interrogerait de vraies bases de données de crédit
    
    logger.info(f"🔍 Évaluation crédit pour demande {demande_id}...")
    
    # Simuler un délai de traitement
    await asyncio.sleep(1)
    
    # Générer un score de crédit réaliste basé sur le revenu
    base_score = 550 + (revenu_annuel / 1000)
    score_credit = int(min(850, max(300, base_score + random.randint(-50, 50))))
    
    # Vérifier les antécédents (simulation)
    antecedents_positifs = score_credit >= 600
    
    # Simuler des dettes existantes (0-30% du revenu)
    dettes_existantes = revenu_annuel * random.uniform(0, 0.3)
    
    # Calculer le ratio dette/revenu
    mensualite_estimee = montant_demande / 240  # Sur 20 ans
    ratio_dette_revenu = ((dettes_existantes / 12 + mensualite_estimee) / (revenu_annuel / 12)) * 100
    
    evaluation = EvaluationCredit(
        demande_id=demande_id,
        score_credit=score_credit,
        antecedents_positifs=antecedents_positifs,
        dettes_existantes=dettes_existantes,
        ratio_dette_revenu=round(ratio_dette_revenu, 2)
    )
    
    logger.info(f"✓ Crédit évalué: Score={score_credit}, Ratio={ratio_dette_revenu:.2f}%")
    
    return evaluation


async def handle_demande_created(event: Event):
    """
    Handler pour l'événement demande.created
    Déclenche l'évaluation du crédit via Celery task
    """
    demande_id = event.demande_id
    data = event.data
    
    logger.info(f"📨 Traitement demande.created: {demande_id}")
    
    try:
        # Launch Celery task asynchronously
        task = evaluer_credit_task.apply_async(
            args=[
                demande_id,
                data.get("client_id"),
                data.get("montant_demande"),
                data.get("revenu_annuel"),
                event.correlation_id
            ],
            task_id=f"credit-{demande_id}-{event.correlation_id[:8]}"
        )
        
        logger.info(f"✓ Celery task lancée: {task.id} pour demande {demande_id}")
        
        # No need to publish here - handled by the Celery task
        
    except Exception as e:
        logger.error(f"✗ Erreur lors du lancement de la tâche Celery: {e}")
        
        # Publier un événement d'échec si impossible de lancer la tâche
        if event_publisher:
            await event_publisher.publish(
                event_type="credit.evaluation.failed",
                demande_id=demande_id,
                data={"error": f"Failed to launch Celery task: {str(e)}"},
                correlation_id=event.correlation_id
            )


async def handle_compensation(event: Event):
    """
    Handler pour les événements de compensation
    Annule l'évaluation crédit si une étape ultérieure échoue
    """
    demande_id = event.demande_id
    etape_echec = event.data.get("etape_echec")
    correlation_id = event.correlation_id
    
    logger.warning(f"⚠️ [Service Crédit] Compensation déclenchée: {demande_id} - Échec: {etape_echec}")
    
    # Vérifier si on doit compenser (seulement si bien ou décision a échoué)
    if etape_echec not in ["evaluation_bien", "prise_decision"]:
        logger.info(f"⚠️ [Service Crédit] Pas de compensation nécessaire pour {etape_echec}")
        return
    
    # En production, on annulerait :
    #    - La réservation de crédit auprès de l'organisme externe
    #    - Le score calculé
    #    - Les allocations de ressources
    
    # Publier un événement d'annulation
    if event_publisher:
        await event_publisher.publish(
            event_type="credit.cancelled",
            demande_id=demande_id,
            data={
                "raison": f"Compensation suite à échec de {etape_echec}",
                "correlation_id": correlation_id
            },
            correlation_id=correlation_id
        )
        
        logger.info(f"✓ [Service Crédit] Événement credit.cancelled publié pour {demande_id}")
    
    logger.warning(f"⚠️ [Service Crédit] Évaluation crédit annulée pour demande {demande_id}")


async def start_consumer():
    """Démarre le consumer d'événements"""
    global event_consumer
    
    if rabbitmq_client:
        event_consumer = EventConsumer(rabbitmq_client, "service_credit_queue")
        
        # Enregistrer les handlers
        event_consumer.register_handler("demande.created", handle_demande_created)
        event_consumer.register_handler("compensation.triggered", handle_compensation)
        
        # Démarrer la consommation (bloquant)
        await event_consumer.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    global rabbitmq_client, event_publisher
    
    # Startup
    logger.info("🚀 Démarrage du Service Crédit...")
    
    # Connexion à RabbitMQ
    rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
    rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5672"))
    rabbitmq_user = os.getenv("RABBITMQ_USER", "guest")
    rabbitmq_password = os.getenv("RABBITMQ_PASSWORD", "guest")
    
    rabbitmq_client = RabbitMQClient(
        host=rabbitmq_host,
        port=rabbitmq_port,
        user=rabbitmq_user,
        password=rabbitmq_password
    )
    
    await rabbitmq_client.connect()
    event_publisher = EventPublisher(rabbitmq_client)
    
    # Démarrer le consumer dans une tâche background
    asyncio.create_task(start_consumer())
    
    logger.info("✓ Service Crédit prêt")
    
    yield
    
    # Shutdown
    logger.info("🛑 Arrêt du Service Crédit...")
    if rabbitmq_client:
        await rabbitmq_client.disconnect()


app = FastAPI(
    title="Service Crédit",
    description="Service d'évaluation des antécédents de crédit",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "credit",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/credit/evaluer")
async def evaluer_credit_endpoint(demande_id: str, client_id: str, 
                                  montant_demande: float, revenu_annuel: float) -> dict:
    """
    Endpoint manuel pour évaluer le crédit
    Lance une tâche Celery et retourne immédiatement le task_id
    """
    try:
        # Launch Celery task
        task = evaluer_credit_task.apply_async(
            args=[demande_id, client_id, montant_demande, revenu_annuel, demande_id],
            task_id=f"credit-manual-{demande_id}"
        )
        
        logger.info(f"✓ Celery task lancée: {task.id}")
        
        return {
            "task_id": task.id,
            "demande_id": demande_id,
            "status": "PENDING",
            "message": "Credit evaluation task submitted successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/credit/task/{task_id}")
async def get_task_status(task_id: str) -> dict:
    """
    Vérifier le statut d'une tâche Celery
    """
    from celery.result import AsyncResult
    from celery_app import celery_app
    
    task_result = AsyncResult(task_id, app=celery_app)
    
    response = {
        "task_id": task_id,
        "status": task_result.status,
        "result": None,
        "error": None
    }
    
    if task_result.ready():
        if task_result.successful():
            response["result"] = task_result.result
        else:
            response["error"] = str(task_result.info)
    
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

