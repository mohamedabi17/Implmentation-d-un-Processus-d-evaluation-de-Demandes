"""
Repository layer for database operations
"""
import logging
from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from db_models import DemandeDB, ProcessedMessageDB, SagaStateDB

import sys
sys.path.append('/app')
from shared.models import Demande, DemandeCreate, StatutDemande, Decision

logger = logging.getLogger(__name__)


class DemandeRepository:
    """Repository for loan request operations"""
    
    @staticmethod
    async def create(session: AsyncSession, demande) -> DemandeDB:
        """
        Create a new loan request
        
        Args:
            session: Database session
            demande: Loan request data (dict or Demande object)
            
        Returns:
            DemandeDB: Created database model
        """
        # Handle both dict and Demande object
        if isinstance(demande, dict):
            # Filter dict to only include valid DemandeDB columns
            valid_columns = {
                'id', 'client_id', 'montant_demande', 'revenu_annuel', 
                'duree_pret_mois', 'adresse_bien', 'statut',
                'score_credit', 'antecedents_positifs', 'dettes_existantes', 'ratio_dette_revenu',
                'valeur_bien', 'valeur_cadastrale', 'etat_bien', 'zone_geographique', 'ratio_pret_valeur',
                'decision', 'raison_decision', 'score_global', 'taux_interet_propose',
                'conditions_supplementaires', 'created_at', 'updated_at'
            }
            filtered_data = {k: v for k, v in demande.items() if k in valid_columns}
            db_demande = DemandeDB(**filtered_data)
        else:
            db_demande = DemandeDB(
                id=demande.id,
                client_id=demande.client_id,
                montant_demande=demande.montant_demande,
                revenu_annuel=demande.revenu_annuel,
                duree_pret_mois=demande.duree_pret_mois,
                adresse_bien=demande.adresse_bien,
                statut=demande.statut,
                created_at=demande.created_at,
                updated_at=demande.updated_at
            )
        
        session.add(db_demande)
        await session.flush()  # Don't commit in repository methods
        
        logger.info(f"✓ Demande créée en DB: {db_demande.id}")
        return db_demande
    
    @staticmethod
    async def get_by_id(session: AsyncSession, demande_id: str) -> Optional[DemandeDB]:
        """Get loan request by ID"""
        result = await session.execute(
            select(DemandeDB).where(DemandeDB.id == demande_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_client_id(session: AsyncSession, client_id: str) -> List[DemandeDB]:
        """Get all loan requests for a client"""
        result = await session.execute(
            select(DemandeDB).where(DemandeDB.client_id == client_id)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_all(session: AsyncSession) -> List[DemandeDB]:
        """Get all loan requests"""
        result = await session.execute(select(DemandeDB))
        return result.scalars().all()
    
    @staticmethod
    async def update_status(session: AsyncSession, demande_id: str, 
                           nouveau_statut: StatutDemande) -> Optional[DemandeDB]:
        """Update loan request status"""
        db_demande = await DemandeRepository.get_by_id(session, demande_id)
        if db_demande:
            db_demande.statut = nouveau_statut
            db_demande.updated_at = datetime.utcnow()
            await session.flush()  # Don't commit in repository
            logger.info(f"✓ Statut mis à jour en DB: {demande_id} → {nouveau_statut}")
        return db_demande
    
    @staticmethod
    async def update_credit_evaluation(session: AsyncSession, demande_id: str,
                                      score_credit: int, antecedents_positifs: bool,
                                      dettes_existantes: float, ratio_dette_revenu: float) -> Optional[DemandeDB]:
        """
        Update loan request with credit evaluation results
        
        NOTE: Commit is controlled by caller. This method only modifies the object.
        Caller must commit the transaction.
        """
        db_demande = await DemandeRepository.get_by_id(session, demande_id)
        if db_demande:
            db_demande.score_credit = score_credit
            db_demande.antecedents_positifs = antecedents_positifs
            db_demande.dettes_existantes = dettes_existantes
            db_demande.ratio_dette_revenu = ratio_dette_revenu
            db_demande.statut = StatutDemande.VERIFICATION_CREDIT
            db_demande.updated_at = datetime.utcnow()
            # ❌ REMOVED: await session.commit()
            # ❌ REMOVED: await session.refresh(db_demande)
            logger.info(f"✓ Évaluation crédit modifiée (commit contrôlé par l'appelant): {demande_id}")
        return db_demande
    
    @staticmethod
    async def update_property_evaluation(session: AsyncSession, demande_id: str,
                                        valeur_bien: float, valeur_cadastrale: float,
                                        etat_bien: str, zone_geographique: str,
                                        ratio_pret_valeur: float) -> Optional[DemandeDB]:
        """
        Update loan request with property evaluation results
        
        NOTE: Commit is controlled by caller. This method only modifies the object.
        Caller must commit the transaction.
        """
        db_demande = await DemandeRepository.get_by_id(session, demande_id)
        if db_demande:
            db_demande.valeur_bien = valeur_bien
            db_demande.valeur_cadastrale = valeur_cadastrale
            db_demande.etat_bien = etat_bien
            db_demande.zone_geographique = zone_geographique
            db_demande.ratio_pret_valeur = ratio_pret_valeur
            db_demande.statut = StatutDemande.EVALUATION_BIEN
            db_demande.updated_at = datetime.utcnow()
            # ❌ REMOVED: await session.commit()
            # ❌ REMOVED: await session.refresh(db_demande)
            logger.info(f"✓ Évaluation bien modifiée (commit contrôlé par l'appelant): {demande_id}")
        return db_demande
    
    @staticmethod
    async def update_decision(session: AsyncSession, demande_id: str,
                             decision: Decision, raison: str, score_global: float,
                             taux_interet: Optional[float] = None,
                             conditions: Optional[str] = None) -> Optional[DemandeDB]:
        """
        Update loan request with final decision
        
        NOTE: Commit is controlled by caller. This method only modifies the object.
        Caller must commit the transaction.
        """
        db_demande = await DemandeRepository.get_by_id(session, demande_id)
        if db_demande:
            db_demande.decision = decision
            db_demande.raison_decision = raison
            db_demande.score_global = score_global
            db_demande.taux_interet_propose = taux_interet
            db_demande.conditions_supplementaires = conditions
            
            # Update status based on decision
            if decision == Decision.APPROUVE:
                db_demande.statut = StatutDemande.APPROUVE
            elif decision == Decision.REJETE:
                db_demande.statut = StatutDemande.REJETE
            else:
                db_demande.statut = StatutDemande.EN_DECISION
            
            db_demande.updated_at = datetime.utcnow()
            # ❌ REMOVED: await session.commit()
            # ❌ REMOVED: await session.refresh(db_demande)
            logger.info(f"✓ Décision modifiée (commit contrôlé par l'appelant): {demande_id} → {decision}")
        return db_demande
    
    @staticmethod
    async def delete(session: AsyncSession, demande_id: str) -> bool:
        """Delete (cancel) a loan request"""
        db_demande = await DemandeRepository.get_by_id(session, demande_id)
        if db_demande:
            db_demande.statut = StatutDemande.ANNULE
            db_demande.updated_at = datetime.utcnow()
            await session.flush()  # Don't commit in repository
            logger.info(f"✓ Demande annulée en DB: {demande_id}")
            return True
        return False
    
    @staticmethod
    def to_pydantic(db_demande: DemandeDB) -> Demande:
        """Convert database model to Pydantic model"""
        return Demande(
            id=db_demande.id,
            client_id=db_demande.client_id,
            montant_demande=db_demande.montant_demande,
            revenu_annuel=db_demande.revenu_annuel,
            duree_pret_mois=db_demande.duree_pret_mois,
            adresse_bien=db_demande.adresse_bien,
            statut=db_demande.statut,
            score_credit=db_demande.score_credit,
            valeur_bien=db_demande.valeur_bien,
            decision=db_demande.decision,
            raison_decision=db_demande.raison_decision,
            created_at=db_demande.created_at,
            updated_at=db_demande.updated_at
        )


class IdempotencyRepository:
    """Repository for idempotency tracking"""
    
    @staticmethod
    async def is_processed(session: AsyncSession, correlation_id: str) -> bool:
        """
        Check if message was already processed
        
        WARNING: This method has a race condition when used with separate commits.
        Prefer using try_mark_as_processed() for atomic check-and-mark.
        """
        result = await session.execute(
            select(ProcessedMessageDB).where(
                ProcessedMessageDB.correlation_id == correlation_id
            )
        )
        return result.scalar_one_or_none() is not None
    
    @staticmethod
    async def try_mark_as_processed(session: AsyncSession, correlation_id: str,
                                     event_type: str, demande_id: str,
                                     processor_service: str) -> bool:
        """
        Atomically try to mark message as processed using INSERT ON CONFLICT.
        
        This method solves the race condition by using PostgreSQL's INSERT ON CONFLICT
        to atomically check and insert in a single database operation.
        
        Args:
            session: Database session (must be in active transaction)
            correlation_id: Unique correlation ID for the message
            event_type: Type of event being processed
            demande_id: Associated demande ID
            processor_service: Name of the processing service
            
        Returns:
            True if this worker successfully marked the message (should process)
            False if message was already marked by another worker (skip processing)
        """
        from sqlalchemy import text
        
        # Use raw SQL with ON CONFLICT for atomic operation
        # RETURNING clause tells us if the INSERT actually happened
        query = text("""
            INSERT INTO processed_messages 
                (correlation_id, event_type, demande_id, processor_service, processed_at)
            VALUES 
                (:correlation_id, :event_type, :demande_id, :processor_service, NOW())
            ON CONFLICT (correlation_id) DO NOTHING
            RETURNING correlation_id
        """)
        
        result = await session.execute(query, {
            "correlation_id": correlation_id,
            "event_type": event_type,
            "demande_id": demande_id,
            "processor_service": processor_service
        })
        
        # If RETURNING clause returns a row, the INSERT succeeded (we won the race)
        # If no row returned, another worker already inserted it (we lost the race)
        inserted = result.scalar_one_or_none()
        
        if inserted:
            logger.info(f"✓ Message marqué comme traité (atomic): {correlation_id}")
            return True
        else:
            logger.info(f"⚠️ Message déjà traité par un autre worker: {correlation_id}")
            return False
    
    @staticmethod
    async def mark_as_processed(session: AsyncSession, correlation_id: str,
                                event_type: str, demande_id: str,
                                processor_service: str) -> ProcessedMessageDB:
        """
        Mark message as processed (non-atomic version - deprecated)
        
        WARNING: This method should NOT be used in event consumers due to race condition.
        Use try_mark_as_processed() instead for atomic check-and-mark.
        
        This method is kept for backward compatibility but should be removed after migration.
        """
        processed_msg = ProcessedMessageDB(
            correlation_id=correlation_id,
            event_type=event_type,
            demande_id=demande_id,
            processor_service=processor_service,
            processed_at=datetime.utcnow()
        )
        
        session.add(processed_msg)
        # ❌ REMOVED: await session.commit()
        # ❌ REMOVED: await session.refresh(processed_msg)
        
        logger.info(f"✓ Message ajouté (commit contrôlé par l'appelant): {correlation_id}")
        return processed_msg


class SagaRepository:
    """Repository for saga state management"""
    
    @staticmethod
    async def create(session: AsyncSession, saga_id: str, demande_id: str,
                    total_steps: int, steps_data: str = "[]") -> SagaStateDB:
        """Create new saga state"""
        saga_state = SagaStateDB(
            saga_id=saga_id,
            demande_id=demande_id,
            total_steps=total_steps,
            steps_data=steps_data,
            created_at=datetime.utcnow()
        )
        
        session.add(saga_state)
        await session.flush()  # Don't commit in repository
        
        logger.info(f"✓ Saga créée en DB: {saga_id}")
        return saga_state
    
    @staticmethod
    async def get_by_id(session: AsyncSession, saga_id: str) -> Optional[SagaStateDB]:
        """Get saga state by ID"""
        result = await session.execute(
            select(SagaStateDB).where(SagaStateDB.saga_id == saga_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def update(session: AsyncSession, saga_id: str,
                    current_step_index: int = None,
                    completed: bool = None,
                    failed: bool = None,
                    compensated: bool = None,
                    steps_data: str = None,
                    failed_step_name: str = None,
                    failure_reason: str = None) -> Optional[SagaStateDB]:
        """Update saga state"""
        saga_state = await SagaRepository.get_by_id(session, saga_id)
        if saga_state:
            if current_step_index is not None:
                saga_state.current_step_index = current_step_index
            if completed is not None:
                saga_state.completed = completed
                if completed:
                    saga_state.completed_at = datetime.utcnow()
            if failed is not None:
                saga_state.failed = failed
            if compensated is not None:
                saga_state.compensated = compensated
            if steps_data is not None:
                saga_state.steps_data = steps_data
            if failed_step_name is not None:
                saga_state.failed_step_name = failed_step_name
            if failure_reason is not None:
                saga_state.failure_reason = failure_reason
            
            saga_state.updated_at = datetime.utcnow()
            await session.flush()  # Don't commit in repository
            logger.info(f"✓ Saga mise à jour: {saga_id}")
        return saga_state


# Standalone function wrappers for backward compatibility

async def create_demande(session: AsyncSession, demande: Demande) -> DemandeDB:
    """Create a new loan request"""
    return await DemandeRepository.create(session, demande)


async def get_demande_by_id(session: AsyncSession, demande_id: str) -> Optional[DemandeDB]:
    """Get loan request by ID"""
    return await DemandeRepository.get_by_id(session, demande_id)


async def update_demande_status(session: AsyncSession, demande_id: str, 
                                nouveau_statut: StatutDemande) -> Optional[DemandeDB]:
    """Update loan request status"""
    return await DemandeRepository.update_status(session, demande_id, nouveau_statut)


async def update_credit_evaluation(session: AsyncSession, demande_id: str,
                                   score_credit: int, antecedents_positifs: bool,
                                   dettes_existantes: float, ratio_dette_revenu: float) -> Optional[DemandeDB]:
    """Update loan request with credit evaluation results"""
    return await DemandeRepository.update_credit_evaluation(
        session, demande_id, score_credit, antecedents_positifs, 
        dettes_existantes, ratio_dette_revenu
    )


async def update_property_evaluation(session: AsyncSession, demande_id: str,
                                     valeur_bien: float, valeur_cadastrale: float,
                                     etat_bien: str, zone_geographique: str,
                                     ratio_pret_valeur: float) -> Optional[DemandeDB]:
    """Update loan request with property evaluation results"""
    return await DemandeRepository.update_property_evaluation(
        session, demande_id, valeur_bien, valeur_cadastrale,
        etat_bien, zone_geographique, ratio_pret_valeur
    )


async def update_decision(session: AsyncSession, demande_id: str,
                         decision: Decision, raison_decision: str,
                         score_global: float, taux_interet_propose: float,
                         conditions_supplementaires: str = None) -> Optional[DemandeDB]:
    """Update loan request with final decision"""
    return await DemandeRepository.update_decision(
        session, demande_id, decision, raison_decision,
        score_global, taux_interet_propose, conditions_supplementaires
    )


async def try_mark_as_processed(session: AsyncSession, correlation_id: str,
                                event_type: str, demande_id: str,
                                processor_service: str) -> bool:
    """Try to mark message as processed (idempotency check)"""
    return await IdempotencyRepository.try_mark_as_processed(
        session, correlation_id, event_type, demande_id, processor_service
    )
