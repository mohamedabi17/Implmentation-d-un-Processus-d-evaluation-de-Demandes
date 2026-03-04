"""
Enhanced Saga Pattern with Database Persistence
Upgrades the existing Saga implementation to persist state in PostgreSQL
"""
import json
import logging
from typing import Dict, List, Callable, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

import sys
sys.path.append('/app')

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
    
    def to_dict(self) -> dict:
        """Serialize step state to dict"""
        return {
            "name": self.name,
            "executed": self.executed,
            "compensated": self.compensated
        }
    
    @classmethod
    def from_dict(cls, data: dict, execute_fn: Callable, compensate_fn: Callable):
        """Deserialize step from dict"""
        step = cls(data["name"], execute_fn, compensate_fn)
        step.executed = data.get("executed", False)
        step.compensated = data.get("compensated", False)
        return step


class PersistentSagaOrchestrator:
    """
    Orchestrateur de Saga avec persistence en base de données
    
    Implémente le pattern Saga pour garantir la cohérence des données
    avec persistence de l'état pour recovery en cas de crash
    """
    
    def __init__(self, saga_id: str, demande_id: str, 
                 event_publisher: EventPublisher,
                 db_session: AsyncSession):
        """
        Initialise l'orchestrateur avec persistence
        
        Args:
            saga_id: Identifiant unique de la saga
            demande_id: ID de la demande associée
            event_publisher: Publisher pour les événements
            db_session: Session de base de données pour persistence
        """
        self.saga_id = saga_id
        self.demande_id = demande_id
        self.event_publisher = event_publisher
        self.db_session = db_session
        self.steps: List[SagaStep] = []
        self.current_step_index = 0
        self.failed = False
        self.completed = False
        self.compensated = False
    
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
    
    async def _persist_state(self):
        """Persist saga state to database"""
        from services.demandes.repository import SagaRepository
        
        # Serialize steps
        steps_data = json.dumps([step.to_dict() for step in self.steps])
        
        # Check if saga exists
        existing = await SagaRepository.get_by_id(self.db_session, self.saga_id)
        
        if existing is None:
            # Create new
            await SagaRepository.create(
                self.db_session,
                saga_id=self.saga_id,
                demande_id=self.demande_id,
                total_steps=len(self.steps),
                steps_data=steps_data
            )
        else:
            # Update existing
            await SagaRepository.update(
                self.db_session,
                saga_id=self.saga_id,
                current_step_index=self.current_step_index,
                completed=self.completed,
                failed=self.failed,
                compensated=self.compensated,
                steps_data=steps_data
            )
    
    async def _load_state(self):
        """Load saga state from database"""
        from services.demandes.repository import SagaRepository
        
        saga_state = await SagaRepository.get_by_id(self.db_session, self.saga_id)
        
        if saga_state:
            self.current_step_index = saga_state.current_step_index
            self.completed = saga_state.completed
            self.failed = saga_state.failed
            self.compensated = saga_state.compensated
            
            # Deserialize steps (requires registered functions)
            if saga_state.steps_data:
                steps_list = json.loads(saga_state.steps_data)
                # This is a limitation - in production use task names/IDs
                logger.info(f"✓ Loaded saga state: {self.saga_id}")
    
    async def execute(self) -> bool:
        """
        Exécute la saga avec persistence
        
        Returns:
            True si succès, False si échec
        """
        logger.info(f"🚀 Démarrage de la saga {self.saga_id}")
        
        # Persist initial state
        await self._persist_state()
        
        try:
            # Exécuter chaque étape
            for index, step in enumerate(self.steps):
                self.current_step_index = index
                
                logger.info(f"▶️  Exécution étape {index + 1}/{len(self.steps)}: {step.name}")
                
                try:
                    # Exécuter l'étape
                    await step.execute()
                    step.executed = True
                    
                    # Persist after each step
                    await self._persist_state()
                    
                    logger.info(f"✓ Étape {step.name} réussie")
                    
                except Exception as e:
                    # Échec de l'étape
                    logger.error(f"✗ Échec de l'étape {step.name}: {e}")
                    self.failed = True
                    
                    # Persist failure state
                    from services.demandes.repository import SagaRepository
                    await SagaRepository.update(
                        self.db_session,
                        saga_id=self.saga_id,
                        failed=True,
                        failed_step_name=step.name,
                        failure_reason=str(e)
                    )
                    
                    # Déclencher la compensation
                    await self._compensate(index)
                    
                    # Publier événement de compensation
                    await self.event_publisher.publish(
                        event_type="compensation.triggered",
                        demande_id=self.demande_id,
                        data={
                            "saga_id": self.saga_id,
                            "etape_echec": step.name,
                            "raison": str(e),
                            "etapes_compensees": index
                        },
                        correlation_id=self.saga_id
                    )
                    
                    return False
            
            # Toutes les étapes ont réussi
            self.completed = True
            await self._persist_state()
            
            logger.info(f"✓ Saga {self.saga_id} complétée avec succès")
            return True
            
        except Exception as e:
            logger.error(f"✗ Erreur fatale dans la saga {self.saga_id}: {e}")
            self.failed = True
            await self._persist_state()
            await self._compensate(self.current_step_index)
            return False
    
    async def _compensate(self, failed_step_index: int):
        """
        Compenser les étapes déjà exécutées avec persistence
        
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
                    
                    # Persist compensation
                    await self._persist_state()
                    
                    logger.info(f"✓ Compensation de {step.name} réussie")
                    
                except Exception as e:
                    logger.error(f"✗ Échec de la compensation de {step.name}: {e}")
                    # Continuer malgré l'échec de compensation
        
        # Mark as compensated
        self.compensated = True
        await self._persist_state()
        
        # Publier événement de compensation complétée
        await self.event_publisher.publish(
            event_type="compensation.completed",
            demande_id=self.demande_id,
            data={
                "saga_id": self.saga_id,
                "etapes_compensees": failed_step_index + 1,
                "timestamp": datetime.utcnow().isoformat()
            },
            correlation_id=self.saga_id
        )
        
        logger.info(f"✓ Compensation complétée pour saga {self.saga_id}")


class SagaRegistry:
    """
    Registre pour suivre toutes les sagas actives
    Enhanced with database persistence
    """
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.sagas: Dict[str, PersistentSagaOrchestrator] = {}
    
    def register(self, saga: PersistentSagaOrchestrator):
        """Enregistrer une saga en mémoire"""
        self.sagas[saga.saga_id] = saga
        logger.info(f"Saga enregistrée: {saga.saga_id}")
    
    def get(self, saga_id: str) -> Optional[PersistentSagaOrchestrator]:
        """Récupérer une saga"""
        return self.sagas.get(saga_id)
    
    def remove(self, saga_id: str):
        """Supprimer une saga"""
        if saga_id in self.sagas:
            del self.sagas[saga_id]
            logger.info(f"Saga supprimée: {saga_id}")
    
    async def get_active_sagas_from_db(self) -> List[dict]:
        """Obtenir toutes les sagas actives depuis la DB"""
        from services.demandes.repository import SagaRepository
        from sqlalchemy import select
        from services.demandes.db_models import SagaStateDB
        
        result = await self.db_session.execute(
            select(SagaStateDB).where(
                (SagaStateDB.completed == False) & (SagaStateDB.failed == False)
            )
        )
        
        active_sagas = result.scalars().all()
        return [
            {
                "saga_id": s.saga_id,
                "demande_id": s.demande_id,
                "current_step": s.current_step_index,
                "total_steps": s.total_steps,
                "created_at": s.created_at.isoformat()
            }
            for s in active_sagas
        ]
    
    async def get_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques depuis la DB"""
        from sqlalchemy import select, func
        from services.demandes.db_models import SagaStateDB
        
        result = await self.db_session.execute(
            select(
                func.count(SagaStateDB.saga_id).label('total'),
                func.sum(func.cast(SagaStateDB.completed, type=int)).label('completed'),
                func.sum(func.cast(SagaStateDB.failed, type=int)).label('failed')
            )
        )
        
        row = result.first()
        
        return {
            "total": row.total or 0,
            "completed": row.completed or 0,
            "failed": row.failed or 0,
            "active": (row.total or 0) - (row.completed or 0) - (row.failed or 0)
        }
