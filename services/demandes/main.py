"""
Service Demandes - Point d'entrée pour les demandes de prêt immobilier
WITH POSTGRESQL PERSISTENCE
"""
import os
import uuid
import logging
from datetime import datetime
from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

import sys
sys.path.append('/app')

from shared.models import DemandeCreate, Demande, StatutDemande
from shared.rabbitmq import RabbitMQClient, EventPublisher
from shared.events import create_event
from database import get_db, init_db, close_db
from repository import DemandeRepository
from event_consumer import start_consumer

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Client RabbitMQ
rabbitmq_client: RabbitMQClient | None = None
event_publisher: EventPublisher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    global rabbitmq_client, event_publisher
    
    # Startup
    logger.info("🚀 Démarrage du Service Demandes...")
    
    # Initialize database
    logger.info("📊 Initialisation de la base de données...")
    await init_db()
    logger.info("✓ Base de données initialisée")
    
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
    
    # Start event consumer in background
    asyncio.create_task(start_consumer(rabbitmq_client))
    
    logger.info("✓ Service Demandes prêt")
    
    yield
    
    # Shutdown
    logger.info("🛑 Arrêt du Service Demandes...")
    if rabbitmq_client:
        await rabbitmq_client.disconnect()
    
    # Close database
    await close_db()
    logger.info("✓ Connexions base de données fermées")


app = FastAPI(
    title="Service Demandes",
    description="Service de gestion des demandes de prêt immobilier",
    version="1.0.0",
    lifespan=lifespan
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "demandes",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/demandes", status_code=status.HTTP_201_CREATED)
async def creer_demande(demande_data: DemandeCreate, db: AsyncSession = Depends(get_db)) -> Demande:
    """
    Créer une nouvelle demande de prêt immobilier
    
    Args:
        demande_data: Données de la demande
        db: Database session
        
    Returns:
        La demande créée
    """
    try:
        # Générer un ID unique
        demande_id = f"DEM-{uuid.uuid4().hex[:8].upper()}"
        
        # Créer la demande
        demande = Demande(
            id=demande_id,
            **demande_data.model_dump()
        )
        
        # Sauvegarder en base de données PostgreSQL
        await DemandeRepository.create(db, demande)
        
        logger.info(f"✓ Demande créée: {demande_id} - Client: {demande.client_id}")
        
        # Publier l'événement demande.created
        if event_publisher:
            await event_publisher.publish(
                event_type="demande.created",
                demande_id=demande_id,
                data={
                    "client_id": demande.client_id,
                    "montant_demande": demande.montant_demande,
                    "revenu_annuel": demande.revenu_annuel,
                    "duree_pret_mois": demande.duree_pret_mois,
                    "adresse_bien": demande.adresse_bien
                },
                correlation_id=demande_id
            )
        
        return demande
        
    except Exception as e:
        logger.error(f"✗ Erreur lors de la création de la demande: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création de la demande: {str(e)}"
        )


@app.get("/demandes/{demande_id}")
async def obtenir_demande(demande_id: str, db: AsyncSession = Depends(get_db)) -> Demande:
    """
    Obtenir les détails d'une demande
    
    Args:
        demande_id: ID de la demande
        db: Database session
        
    Returns:
        La demande
    """
    db_demande = await DemandeRepository.get_by_id(db, demande_id)
    
    if not db_demande:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Demande {demande_id} introuvable"
        )
    
    return DemandeRepository.to_pydantic(db_demande)


@app.get("/demandes")
async def lister_demandes(client_id: str | None = None, db: AsyncSession = Depends(get_db)) -> List[Demande]:
    """
    Lister toutes les demandes ou filtrer par client
    
    Args:
        client_id: ID du client (optionnel)
        db: Database session
        
    Returns:
        Liste des demandes
    """
    if client_id:
        db_demandes = await DemandeRepository.get_by_client_id(db, client_id)
    else:
        db_demandes = await DemandeRepository.get_all(db)
    
    return [DemandeRepository.to_pydantic(d) for d in db_demandes]


@app.put("/demandes/{demande_id}/statut")
async def mettre_a_jour_statut(
    demande_id: str,
    nouveau_statut: StatutDemande,
    db: AsyncSession = Depends(get_db)
) -> Demande:
    """
    Mettre à jour le statut d'une demande
    
    Args:
        demande_id: ID de la demande
        nouveau_statut: Nouveau statut
        db: Database session
        
    Returns:
        La demande mise à jour
    """
    db_demande = await DemandeRepository.get_by_id(db, demande_id)
    
    if not db_demande:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Demande {demande_id} introuvable"
        )
    
    ancien_statut = db_demande.statut
    db_demande = await DemandeRepository.update_status(db, demande_id, nouveau_statut)
    
    logger.info(f"✓ Statut mis à jour: {demande_id} - {ancien_statut} → {nouveau_statut}")
    
    # Publier l'événement demande.updated
    if event_publisher:
        await event_publisher.publish(
            event_type="demande.updated",
            demande_id=demande_id,
            data={
                "ancien_statut": ancien_statut.value,
                "nouveau_statut": nouveau_statut.value
            },
            correlation_id=demande_id
        )
    
    return DemandeRepository.to_pydantic(db_demande)


@app.delete("/demandes/{demande_id}")
async def annuler_demande(demande_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Annuler une demande
    
    Args:
        demande_id: ID de la demande
        db: Database session
        
    Returns:
        Message de confirmation
    """
    success = await DemandeRepository.delete(db, demande_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Demande {demande_id} introuvable"
        )
    
    logger.info(f"✓ Demande annulée: {demande_id}")
    
    return {"message": f"Demande {demande_id} annulée avec succès"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
