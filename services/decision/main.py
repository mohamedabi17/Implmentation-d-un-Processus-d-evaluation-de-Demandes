"""
Service Décision - Logique d'approbation/rejet basée sur DMN
"""
import os
import logging
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status

import sys
sys.path.append('/app')

from shared.models import ResultatDecision, Decision
from shared.rabbitmq import RabbitMQClient, EventPublisher, EventConsumer
from shared.events import Event
from dmn_rules import DMNDecisionEngine

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Client RabbitMQ
rabbitmq_client: RabbitMQClient | None = None
event_publisher: EventPublisher | None = None
event_consumer: EventConsumer | None = None

# Moteur de décision DMN
dmn_engine = DMNDecisionEngine()


async def prendre_decision(
    demande_id: str,
    score_credit: int,
    ratio_dette_revenu: float,
    montant_demande: float,
    revenu_annuel: float,
    valeur_bien: float,
    ratio_pret_valeur: float
) -> ResultatDecision:
    """
    Prend une décision basée sur les règles DMN
    
    Args:
        demande_id: ID de la demande
        score_credit: Score de crédit
        ratio_dette_revenu: Ratio dette/revenu
        montant_demande: Montant demandé
        revenu_annuel: Revenu annuel
        valeur_bien: Valeur du bien
        ratio_pret_valeur: Ratio prêt/valeur
        
    Returns:
        Résultat de la décision
    """
    logger.info(f"⚖️ Prise de décision pour demande {demande_id}...")
    
    # Simuler un délai de traitement
    await asyncio.sleep(0.5)
    
    # Évaluer selon les règles DMN
    decision, raison, score_global = dmn_engine.evaluer_demande(
        score_credit=score_credit,
        revenu_annuel=revenu_annuel,
        montant_demande=montant_demande,
        ratio_dette_revenu=ratio_dette_revenu,
        valeur_bien=valeur_bien,
        ratio_pret_valeur=ratio_pret_valeur
    )
    
    # Calculer le taux d'intérêt si approuvé
    taux_interet = None
    conditions = None
    
    if decision == Decision.APPROUVE:
        taux_interet = dmn_engine.calculer_taux_interet(score_credit, ratio_pret_valeur)
        
        # Conditions supplémentaires pour certains profils
        if score_credit < 700:
            conditions = "Assurance emprunteur obligatoire avec garantie décès-invalidité"
        elif ratio_pret_valeur > 80:
            conditions = "Garantie hypothécaire renforcée requise"
    
    elif decision == Decision.ETUDE:
        conditions = "Documents supplémentaires requis: justificatifs de revenus des 3 dernières années, attestation d'emploi"
    
    resultat = ResultatDecision(
        demande_id=demande_id,
        decision=decision,
        raison=raison,
        score_global=score_global,
        conditions_supplementaires=conditions,
        taux_interet_propose=taux_interet
    )
    
    logger.info(f"✓ Décision prise: {decision.value} - Score: {score_global:.1f}/100")
    
    return resultat


async def handle_bien_evaluated(event: Event):
    """
    Handler pour l'événement bien.evaluated
    Déclenche la prise de décision finale
    """
    demande_id = event.demande_id
    data = event.data
    
    logger.info(f"📨 Traitement bien.evaluated: {demande_id}")
    
    try:
        # Extraire les données nécessaires
        score_credit = data.get("score_credit", 600)
        valeur_estimee = data.get("valeur_estimee", 0)
        ratio_pret_valeur = data.get("ratio_pret_valeur", 0)
        
        # Valeurs simulées (en production, on récupérerait du service demandes)
        montant_demande = 250000
        revenu_annuel = 60000
        ratio_dette_revenu = 30.0
        
        # Prendre la décision
        resultat = await prendre_decision(
            demande_id=demande_id,
            score_credit=score_credit,
            ratio_dette_revenu=ratio_dette_revenu,
            montant_demande=montant_demande,
            revenu_annuel=revenu_annuel,
            valeur_bien=valeur_estimee,
            ratio_pret_valeur=ratio_pret_valeur
        )
        
        # Publier l'événement decision.made
        if event_publisher:
            await event_publisher.publish(
                event_type="decision.made",
                demande_id=demande_id,
                data={
                    "decision": resultat.decision.value,
                    "raison": resultat.raison,
                    "score_global": resultat.score_global,
                    "conditions_supplementaires": resultat.conditions_supplementaires,
                    "taux_interet_propose": resultat.taux_interet_propose
                },
                correlation_id=event.correlation_id
            )
        
    except Exception as e:
        logger.error(f"✗ Erreur lors de la prise de décision: {e}")
        
        # ✅ SAGA PATTERN : Déclencher la compensation des étapes précédentes
        if event_publisher:
            # Publier l'événement de compensation
            await event_publisher.publish(
                event_type="compensation.triggered",
                demande_id=demande_id,
                data={
                    "etape_echec": "prise_decision",
                    "raison": f"Erreur système lors de la décision: {str(e)}",
                    "service_origine": "service-decision"
                },
                correlation_id=event.correlation_id
            )
            logger.warning(f"⚠️ [Saga] Compensation déclenchée pour {demande_id} - Échec: prise_decision")
            
            # Publier aussi l'événement de décision rejetée
            await event_publisher.publish(
                event_type="decision.made",
                demande_id=demande_id,
                data={
                    "decision": Decision.REJETE.value,
                    "raison": f"Erreur système: {str(e)}",
                    "score_global": 0.0
                },
                correlation_id=event.correlation_id
            )


async def start_consumer():
    """Démarre le consumer d'événements"""
    global event_consumer
    
    if rabbitmq_client:
        event_consumer = EventConsumer(rabbitmq_client, "service_decision_queue")
        
        # Enregistrer les handlers
        event_consumer.register_handler("bien.evaluated", handle_bien_evaluated)
        
        # Démarrer la consommation
        await event_consumer.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    global rabbitmq_client, event_publisher
    
    # Startup
    logger.info("🚀 Démarrage du Service Décision...")
    
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
    
    logger.info("✓ Service Décision prêt")
    
    yield
    
    # Shutdown
    logger.info("🛑 Arrêt du Service Décision...")
    if rabbitmq_client:
        await rabbitmq_client.disconnect()


app = FastAPI(
    title="Service Décision",
    description="Service de prise de décision basé sur DMN",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "decision",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/decision/evaluer")
async def evaluer_decision_endpoint(
    demande_id: str,
    score_credit: int,
    ratio_dette_revenu: float,
    montant_demande: float,
    revenu_annuel: float,
    valeur_bien: float,
    ratio_pret_valeur: float
) -> ResultatDecision:
    """
    Endpoint manuel pour évaluer une décision
    (Utilisé principalement pour les tests)
    """
    try:
        resultat = await prendre_decision(
            demande_id,
            score_credit,
            ratio_dette_revenu,
            montant_demande,
            revenu_annuel,
            valeur_bien,
            ratio_pret_valeur
        )
        return resultat
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/decision/regles")
async def obtenir_regles_dmn():
    """
    Retourne la description des règles DMN
    """
    return {
        "regles": [
            {
                "nom": "Score de crédit",
                "description": "Score FICO entre 300-850",
                "seuils": {
                    "excellent": "≥ 750",
                    "tres_bon": "700-749",
                    "bon": "650-699",
                    "acceptable": "600-649",
                    "insuffisant": "< 600"
                }
            },
            {
                "nom": "Ratio Revenu/Montant",
                "description": "Capacité de remboursement",
                "seuils": {
                    "excellent": "≥ 5x",
                    "tres_bon": "4-5x",
                    "bon": "3-4x",
                    "limite": "2-3x",
                    "insuffisant": "< 2x"
                }
            },
            {
                "nom": "Ratio Dette/Revenu",
                "description": "Endettement total",
                "seuils": {
                    "excellent": "≤ 25%",
                    "bon": "26-30%",
                    "acceptable": "31-35%",
                    "eleve": "36-40%",
                    "trop_eleve": "> 40%"
                }
            },
            {
                "nom": "LTV (Loan to Value)",
                "description": "Ratio prêt/valeur du bien",
                "seuils": {
                    "excellent": "≤ 70%",
                    "bon": "71-80%",
                    "acceptable": "81-90%",
                    "eleve": "91-95%",
                    "trop_eleve": "> 95%"
                }
            }
        ],
        "decisions": {
            "APPROUVE": "Score global ≥ 75 et critères minimums atteints",
            "ETUDE": "Score global 60-74 ou profil nécessitant analyse approfondie",
            "REJETE": "Score global < 60 ou critères minimums non atteints"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
