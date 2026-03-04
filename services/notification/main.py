"""
Service Notification - Communication client via WebSockets/SSE
"""
import os
import logging
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse

import sys
sys.path.append('/app')

from shared.models import NotificationMessage
from shared.rabbitmq import RabbitMQClient, EventPublisher, EventConsumer
from shared.events import Event

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Client RabbitMQ
rabbitmq_client: RabbitMQClient | None = None
event_publisher: EventPublisher | None = None
event_consumer: EventConsumer | None = None

# Gestion des connexions WebSocket
# demande_id -> Set of WebSocket connections
active_connections: Dict[str, Set[WebSocket]] = {}


class ConnectionManager:
    """Gestionnaire de connexions WebSocket"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, demande_id: str):
        """Ajouter une connexion WebSocket"""
        await websocket.accept()
        
        if demande_id not in self.active_connections:
            self.active_connections[demande_id] = set()
        
        self.active_connections[demande_id].add(websocket)
        logger.info(f"✓ Client connecté via WebSocket pour demande {demande_id}")
    
    def disconnect(self, websocket: WebSocket, demande_id: str):
        """Retirer une connexion WebSocket"""
        if demande_id in self.active_connections:
            self.active_connections[demande_id].discard(websocket)
            
            # Nettoyer si plus de connexions
            if not self.active_connections[demande_id]:
                del self.active_connections[demande_id]
        
        logger.info(f"✓ Client déconnecté pour demande {demande_id}")
    
    async def send_to_demande(self, demande_id: str, message: dict):
        """Envoyer un message à tous les clients connectés pour une demande"""
        if demande_id in self.active_connections:
            disconnected = set()
            
            for connection in self.active_connections[demande_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"✗ Erreur lors de l'envoi: {e}")
                    disconnected.add(connection)
            
            # Nettoyer les connexions mortes
            for connection in disconnected:
                self.disconnect(connection, demande_id)


manager = ConnectionManager()


async def envoyer_notification(demande_id: str, type_notification: str, 
                               message: str, data: dict = None):
    """
    Envoyer une notification pour une demande
    
    Args:
        demande_id: ID de la demande
        type_notification: Type de notification
        message: Message de notification
        data: Données supplémentaires
    """
    notification = NotificationMessage(
        demande_id=demande_id,
        type=type_notification,
        message=message,
        data=data or {}
    )
    
    # Envoyer via WebSocket
    await manager.send_to_demande(
        demande_id,
        notification.model_dump(mode='json')
    )
    
    logger.info(f"📤 Notification envoyée: {type_notification} - {demande_id}")


async def handle_demande_created(event: Event):
    """Handler pour l'événement demande.created"""
    demande_id = event.demande_id
    
    await envoyer_notification(
        demande_id,
        "demande_creee",
        "Votre demande de prêt a été créée et est en cours de traitement.",
        {"statut": "EN_ATTENTE"}
    )


async def handle_credit_evaluated(event: Event):
    """Handler pour l'événement credit.evaluated"""
    demande_id = event.demande_id
    data = event.data
    
    score = data.get("score_credit", 0)
    
    await envoyer_notification(
        demande_id,
        "credit_evalue",
        f"Votre crédit a été évalué. Score: {score}",
        {"score_credit": score, "statut": "VERIFICATION_CREDIT"}
    )


async def handle_bien_evaluated(event: Event):
    """Handler pour l'événement bien.evaluated"""
    demande_id = event.demande_id
    data = event.data
    
    valeur = data.get("valeur_estimee", 0)
    
    await envoyer_notification(
        demande_id,
        "bien_evalue",
        f"Votre bien a été évalué à {valeur:,.0f}€",
        {"valeur_estimee": valeur, "statut": "EVALUATION_BIEN"}
    )


async def handle_decision_made(event: Event):
    """Handler pour l'événement decision.made"""
    demande_id = event.demande_id
    data = event.data
    
    decision = data.get("decision")
    raison = data.get("raison")
    taux = data.get("taux_interet_propose")
    
    if decision == "APPROUVE":
        message = f"🎉 Félicitations ! Votre demande de prêt est approuvée à un taux de {taux}%"
    elif decision == "ETUDE":
        message = f"⚠️ Votre demande nécessite une étude approfondie. {raison}"
    else:
        message = f"❌ Votre demande a été rejetée. {raison}"
    
    await envoyer_notification(
        demande_id,
        "decision_prise",
        message,
        {
            "decision": decision,
            "raison": raison,
            "taux_interet": taux,
            "statut": decision
        }
    )


async def handle_compensation(event: Event):
    """Handler pour les événements de compensation"""
    demande_id = event.demande_id
    data = event.data
    
    etape = data.get("etape_echec", "")
    raison = data.get("raison", "")
    
    await envoyer_notification(
        demande_id,
        "erreur_traitement",
        f"⚠️ Une erreur est survenue lors du traitement: {raison}",
        {"etape_echec": etape, "statut": "ECHEC"}
    )


async def start_consumer():
    """Démarre le consumer d'événements"""
    global event_consumer
    
    if rabbitmq_client:
        event_consumer = EventConsumer(rabbitmq_client, "service_notification_queue")
        
        # Enregistrer les handlers pour tous les événements
        event_consumer.register_handler("demande.created", handle_demande_created)
        event_consumer.register_handler("credit.evaluated", handle_credit_evaluated)
        event_consumer.register_handler("bien.evaluated", handle_bien_evaluated)
        event_consumer.register_handler("decision.made", handle_decision_made)
        event_consumer.register_handler("compensation.triggered", handle_compensation)
        
        # Démarrer la consommation
        await event_consumer.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    global rabbitmq_client, event_publisher
    
    # Startup
    logger.info("🚀 Démarrage du Service Notification...")
    
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
    
    logger.info("✓ Service Notification prêt")
    
    yield
    
    # Shutdown
    logger.info("🛑 Arrêt du Service Notification...")
    if rabbitmq_client:
        await rabbitmq_client.disconnect()


app = FastAPI(
    title="Service Notification",
    description="Service de communication client via WebSockets",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "notification",
        "timestamp": datetime.utcnow().isoformat(),
        "active_connections": sum(len(conns) for conns in manager.active_connections.values())
    }


@app.websocket("/ws/{demande_id}")
async def websocket_endpoint(websocket: WebSocket, demande_id: str):
    """
    WebSocket endpoint pour recevoir les notifications en temps réel
    
    Args:
        websocket: Connexion WebSocket
        demande_id: ID de la demande à suivre
    """
    await manager.connect(websocket, demande_id)
    
    try:
        # Envoyer un message de bienvenue
        await websocket.send_json({
            "type": "connection_etablie",
            "message": f"Connecté aux notifications pour la demande {demande_id}",
            "demande_id": demande_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Garder la connexion ouverte
        while True:
            # Attendre des messages du client (ping/pong)
            data = await websocket.receive_text()
            
            # Répondre au ping
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, demande_id)
    except Exception as e:
        logger.error(f"✗ Erreur WebSocket: {e}")
        manager.disconnect(websocket, demande_id)


@app.get("/sse/{demande_id}")
async def sse_endpoint(demande_id: str):
    """
    Server-Sent Events endpoint (alternative à WebSocket)
    
    Args:
        demande_id: ID de la demande à suivre
    """
    async def event_generator():
        # En production, utiliser une vraie implémentation avec queue
        yield f"data: {{'type': 'connection', 'message': 'Connecté aux notifications'}}\n\n"
        
        # Garder la connexion ouverte
        while True:
            await asyncio.sleep(30)
            yield f"data: {{'type': 'heartbeat', 'timestamp': '{datetime.utcnow().isoformat()}'}}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/notifications/send")
async def send_notification_manually(
    demande_id: str,
    type_notification: str,
    message: str
):
    """
    Endpoint manuel pour envoyer une notification
    (Utilisé principalement pour les tests)
    """
    await envoyer_notification(demande_id, type_notification, message)
    return {"status": "sent", "demande_id": demande_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
