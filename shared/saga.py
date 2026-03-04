"""
Gestionnaire de Saga Pattern pour la compensation des transactions distribuées
"""
import logging
from typing import Dict, List, Callable, Any
from datetime import datetime
from shared.events import Event
from shared.rabbitmq import EventPublisher

logger = logging.getLogger(__name__)


class SagaStep:
    """Représente une étape dans une saga"""
    
    def __init__(self, name: str, execute: Callable, compensate: Callable):
        """
        Initialise une étape de saga
        
        Args:
            name: Nom de l'étape
            execute: Fonction d'exécution
            compensate: Fonction de compensation
        """
        self.name = name
        self.execute = execute
        self.compensate = compensate
        self.executed = False
        self.compensated = False


class SagaOrchestrator:
    """
    Orchestrateur de Saga pour gérer les transactions distribuées
    
    Implémente le pattern Saga pour garantir la cohérence des données
    en cas d'échec d'une étape dans le workflow distribué.
    """
    
    def __init__(self, saga_id: str, event_publisher: EventPublisher):
        """
        Initialise l'orchestrateur
        
        Args:
            saga_id: Identifiant unique de la saga
            event_publisher: Publisher pour les événements
        """
        self.saga_id = saga_id
        self.event_publisher = event_publisher
        self.steps: List[SagaStep] = []
        self.current_step_index = 0
        self.failed = False
        self.completed = False
        
    def add_step(self, name: str, execute: Callable, compensate: Callable):
        """
        Ajouter une étape à la saga
        
        Args:
            name: Nom de l'étape
            execute: Fonction d'exécution asynchrone
            compensate: Fonction de compensation asynchrone
        """
        step = SagaStep(name, execute, compensate)
        self.steps.append(step)
        logger.info(f"Étape ajoutée à la saga {self.saga_id}: {name}")
    
    async def execute(self) -> bool:
        """
        Exécute la saga
        
        Returns:
            True si succès, False si échec
        """
        logger.info(f"🚀 Démarrage de la saga {self.saga_id}")
        
        try:
            # Exécuter chaque étape
            for index, step in enumerate(self.steps):
                self.current_step_index = index
                
                logger.info(f"▶️  Exécution étape {index + 1}/{len(self.steps)}: {step.name}")
                
                try:
                    # Exécuter l'étape
                    await step.execute()
                    step.executed = True
                    
                    logger.info(f"✓ Étape {step.name} réussie")
                    
                except Exception as e:
                    # Échec de l'étape
                    logger.error(f"✗ Échec de l'étape {step.name}: {e}")
                    self.failed = True
                    
                    # Déclencher la compensation
                    await self._compensate(index)
                    
                    # Publier événement de compensation
                    await self.event_publisher.publish(
                        event_type="compensation.triggered",
                        demande_id=self.saga_id,
                        data={
                            "etape_echec": step.name,
                            "raison": str(e),
                            "etapes_compensees": index
                        },
                        correlation_id=self.saga_id
                    )
                    
                    return False
            
            # Toutes les étapes ont réussi
            self.completed = True
            logger.info(f"✓ Saga {self.saga_id} complétée avec succès")
            return True
            
        except Exception as e:
            logger.error(f"✗ Erreur fatale dans la saga {self.saga_id}: {e}")
            self.failed = True
            await self._compensate(self.current_step_index)
            return False
    
    async def _compensate(self, failed_step_index: int):
        """
        Compenser les étapes déjà exécutées
        
        Args:
            failed_step_index: Index de l'étape qui a échoué
        """
        logger.warning(f"⚠️  Démarrage de la compensation pour saga {self.saga_id}")
        
        # Compenser dans l'ordre inverse
        for index in range(failed_step_index, -1, -1):
            step = self.steps[index]
            
            if step.executed and not step.compensated:
                logger.info(f"↩️  Compensation de l'étape: {step.name}")
                
                try:
                    await step.compensate()
                    step.compensated = True
                    logger.info(f"✓ Compensation de {step.name} réussie")
                    
                except Exception as e:
                    logger.error(f"✗ Échec de la compensation de {step.name}: {e}")
                    # Continuer malgré l'échec de compensation
        
        # Publier événement de compensation complétée
        await self.event_publisher.publish(
            event_type="compensation.completed",
            demande_id=self.saga_id,
            data={
                "etapes_compensees": failed_step_index + 1,
                "timestamp": datetime.utcnow().isoformat()
            },
            correlation_id=self.saga_id
        )
        
        logger.info(f"✓ Compensation complétée pour saga {self.saga_id}")


class SagaRegistry:
    """
    Registre pour suivre toutes les sagas actives
    """
    
    def __init__(self):
        self.sagas: Dict[str, SagaOrchestrator] = {}
    
    def register(self, saga: SagaOrchestrator):
        """Enregistrer une saga"""
        self.sagas[saga.saga_id] = saga
        logger.info(f"Saga enregistrée: {saga.saga_id}")
    
    def get(self, saga_id: str) -> SagaOrchestrator | None:
        """Récupérer une saga"""
        return self.sagas.get(saga_id)
    
    def remove(self, saga_id: str):
        """Supprimer une saga"""
        if saga_id in self.sagas:
            del self.sagas[saga_id]
            logger.info(f"Saga supprimée: {saga_id}")
    
    def get_active_sagas(self) -> List[SagaOrchestrator]:
        """Obtenir toutes les sagas actives"""
        return [s for s in self.sagas.values() if not s.completed and not s.failed]
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques"""
        total = len(self.sagas)
        completed = len([s for s in self.sagas.values() if s.completed])
        failed = len([s for s in self.sagas.values() if s.failed])
        active = len([s for s in self.sagas.values() if not s.completed and not s.failed])
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "active": active,
            "success_rate": (completed / total * 100) if total > 0 else 0
        }


# Instance globale du registre
saga_registry = SagaRegistry()


async def create_pret_saga(demande_id: str, event_publisher: EventPublisher,
                          demande_data: Dict[str, Any]) -> SagaOrchestrator:
    """
    Créer une saga pour le processus de prêt
    
    Args:
        demande_id: ID de la demande
        event_publisher: Publisher d'événements
        demande_data: Données de la demande
        
    Returns:
        SagaOrchestrator configuré
    """
    saga = SagaOrchestrator(demande_id, event_publisher)
    
    # Étape 1: Évaluation crédit
    async def execute_credit():
        await event_publisher.publish(
            "credit.evaluation.requested",
            demande_id,
            demande_data,
            demande_id
        )
    
    async def compensate_credit():
        logger.info(f"Compensation crédit pour {demande_id}")
        # Annuler la réservation de crédit, etc.
    
    saga.add_step("Évaluation Crédit", execute_credit, compensate_credit)
    
    # Étape 2: Évaluation bien
    async def execute_bien():
        await event_publisher.publish(
            "bien.evaluation.requested",
            demande_id,
            demande_data,
            demande_id
        )
    
    async def compensate_bien():
        logger.info(f"Compensation évaluation bien pour {demande_id}")
        # Annuler l'évaluation, libérer les ressources
    
    saga.add_step("Évaluation Bien", execute_bien, compensate_bien)
    
    # Étape 3: Décision
    async def execute_decision():
        await event_publisher.publish(
            "decision.requested",
            demande_id,
            demande_data,
            demande_id
        )
    
    async def compensate_decision():
        logger.info(f"Compensation décision pour {demande_id}")
        # Annuler la décision
    
    saga.add_step("Prise de Décision", execute_decision, compensate_decision)
    
    # Enregistrer la saga
    saga_registry.register(saga)
    
    return saga
