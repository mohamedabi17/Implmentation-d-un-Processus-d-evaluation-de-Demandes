"""
Service Évaluation Bien - Analyse de la valeur immobilière
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

from shared.models import EvaluationBien
from shared.rabbitmq import RabbitMQClient, EventPublisher, EventConsumer
from shared.events import Event
from tasks import evaluer_bien_task

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Client RabbitMQ
rabbitmq_client: RabbitMQClient | None = None
event_publisher: EventPublisher | None = None
event_consumer: EventConsumer | None = None


async def evaluer_bien(demande_id: str, adresse_bien: str, montant_demande: float) -> EvaluationBien:
    """
    Évaluer un bien immobilier
    
    Args:
        demande_id: ID de la demande
        adresse_bien: Adresse du bien
        montant_demande: Montant demandé pour le prêt
        
    Returns:
        Résultat de l'évaluation du bien
    """
    logger.info(f"🏠 Évaluation du bien pour demande {demande_id}...")
    
    # Simuler un délai de traitement
    await asyncio.sleep(1.5)
    
    # Simulation d'une évaluation immobilière
    # En production, ceci utiliserait des API de cadastre, d'estimation, etc.
    
    # Valeur estimée basée sur le montant demandé avec variation
    variation = random.uniform(0.85, 1.25)
    valeur_estimee = montant_demande * variation
    
    # Valeur cadastrale (généralement légèrement inférieure à l'estimation)
    valeur_cadastrale = valeur_estimee * random.uniform(0.85, 0.95)
    
    # État du bien
    etats = ["Excellent", "Bon", "Moyen", "Mauvais"]
    poids = [0.3, 0.5, 0.15, 0.05]  # Probabilités
    etat_bien = random.choices(etats, weights=poids)[0]
    
    # Zone géographique (simulation)
    zones = ["Centre-ville", "Périphérie", "Banlieue", "Rural"]
    zone_geographique = random.choice(zones)
    
    # Calculer le ratio prêt/valeur (LTV - Loan to Value)
    ratio_pret_valeur = (montant_demande / valeur_estimee) * 100
    
    evaluation = EvaluationBien(
        demande_id=demande_id,
        valeur_estimee=round(valeur_estimee, 2),
        valeur_cadastrale=round(valeur_cadastrale, 2),
        etat_bien=etat_bien,
        zone_geographique=zone_geographique,
        ratio_pret_valeur=round(ratio_pret_valeur, 2)
    )
    
    logger.info(f"✓ Bien évalué: Valeur={valeur_estimee:.0f}€, LTV={ratio_pret_valeur:.2f}%")
    
    return evaluation


async def handle_credit_evaluated(event: Event):
    """
    Handler pour l'événement credit.evaluated
    Déclenche l'évaluation du bien via Celery task
    """
    demande_id = event.demande_id
    data = event.data
    
    logger.info(f"📨 Traitement credit.evaluated: {demande_id}")
    
    try:
        # Extract score_credit from event
        score_credit = data.get("score_credit", 600)
        
        # Simulated values (in production, fetch from service-demandes or database)
        adresse_bien = "Simulation - 123 Rue Example"
        montant_demande = 250000
        
        # Launch Celery task asynchronously
        task = evaluer_bien_task.apply_async(
            args=[
                demande_id,
                adresse_bien,
                montant_demande,
                score_credit,
                event.correlation_id
            ],
            task_id=f"property-{demande_id}-{event.correlation_id[:8]}"
        )
        
        logger.info(f"✓ Celery task lancée: {task.id} pour demande {demande_id}")
        
        
    except Exception as e:
        logger.error(f"✗ Erreur lors du lancement de la tâche Celery: {e}")
        
        # Publier un événement d'échec
        if event_publisher:
            await event_publisher.publish(
                event_type="bien.evaluation.failed",
                demande_id=demande_id,
                data={"error": f"Failed to launch Celery task: {str(e)}"},
                correlation_id=event.correlation_id
            )
            
            # Déclencher la compensation
            await event_publisher.publish(
                event_type="compensation.triggered",
                demande_id=demande_id,
                data={
                    "etape_echec": "evaluation_bien",
                    "raison": str(e)
                },
                correlation_id=event.correlation_id
            )


async def handle_compensation(event: Event):
    """
    Handler pour les événements de compensation
    Annule l'évaluation du bien si la décision échoue
    """
    demande_id = event.demande_id
    etape_echec = event.data.get("etape_echec")
    correlation_id = event.correlation_id
    
    logger.warning(f"⚠️ [Service Bien] Compensation déclenchée: {demande_id} - Échec: {etape_echec}")
    
    # Compenser seulement si la décision a échoué
    if etape_echec != "prise_decision":
        logger.info(f"⚠️ [Service Bien] Pas de compensation nécessaire pour {etape_echec}")
        return
    
    # En production :
    #    - Annuler l'expertise du bien
    #    - Libérer les ressources d'évaluation
    #    - Annuler les réservations d'experts
    
    if event_publisher:
        await event_publisher.publish(
            event_type="bien.cancelled",
            demande_id=demande_id,
            data={
                "raison": f"Compensation suite à échec de {etape_echec}",
                "correlation_id": correlation_id
            },
            correlation_id=correlation_id
        )
        
        logger.info(f"✓ [Service Bien] Événement bien.cancelled publié pour {demande_id}")
    
    logger.warning(f"⚠️ [Service Bien] Évaluation bien annulée pour demande {demande_id}")


async def start_consumer():
    """Démarre le consumer d'événements"""
    global event_consumer
    
    if rabbitmq_client:
        event_consumer = EventConsumer(rabbitmq_client, "service_evaluation_bien_queue")
        
        # Enregistrer les handlers
        event_consumer.register_handler("credit.evaluated", handle_credit_evaluated)
        event_consumer.register_handler("compensation.triggered", handle_compensation)
        
        # Démarrer la consommation
        await event_consumer.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    global rabbitmq_client, event_publisher
    
    # Startup
    logger.info("🚀 Démarrage du Service Évaluation Bien...")
    
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
    
    # Démarrer le consumer
    asyncio.create_task(start_consumer())
    
    logger.info("✓ Service Évaluation Bien prêt")
    
    yield
    
    # Shutdown
    logger.info("🛑 Arrêt du Service Évaluation Bien...")
    if rabbitmq_client:
        await rabbitmq_client.disconnect()


app = FastAPI(
    title="Service Évaluation Bien",
    description="Service d'analyse de la valeur immobilière",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "evaluation_bien",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/bien/evaluer")
async def evaluer_bien_endpoint(demande_id: str, adresse_bien: str, 
                                montant_demande: float) -> dict:
    """
    Endpoint manuel pour évaluer un bien
    Lance une tâche Celery et retourne immédiatement le task_id
    """
    try:
        # Launch Celery task
        task = evaluer_bien_task.apply_async(
            args=[demande_id, adresse_bien, montant_demande, 600, demande_id],
            task_id=f"property-manual-{demande_id}"
        )
        
        logger.info(f"✓ Celery task lancée: {task.id}")
        
        return {
            "task_id": task.id,
            "demande_id": demande_id,
            "status": "PENDING",
            "message": "Property evaluation task submitted successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/bien/task/{task_id}")
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