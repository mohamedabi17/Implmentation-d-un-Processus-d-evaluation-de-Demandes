"""
SQLAlchemy Database Models
"""
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, Enum as SQLEnum, Boolean
from database import Base

import sys
sys.path.append('/app')
from shared.models import StatutDemande, Decision


class DemandeDB(Base):
    """
    SQLAlchemy model for loan requests
    """
    __tablename__ = "demandes"
    __table_args__ = {'extend_existing': True}
    
    # Primary key
    id = Column(String(50), primary_key=True)
    
    # Client information
    client_id = Column(String(100), nullable=False, index=True)
    
    # Loan details
    montant_demande = Column(Float, nullable=False)
    revenu_annuel = Column(Float, nullable=False)
    duree_pret_mois = Column(Integer, nullable=False)
    adresse_bien = Column(String(500), nullable=False)
    
    # Status tracking
    statut = Column(SQLEnum(StatutDemande), nullable=False, default=StatutDemande.EN_ATTENTE, index=True)
    
    # Evaluation results
    score_credit = Column(Integer, nullable=True)
    antecedents_positifs = Column(Boolean, nullable=True)
    dettes_existantes = Column(Float, nullable=True)
    ratio_dette_revenu = Column(Float, nullable=True)
    
    valeur_bien = Column(Float, nullable=True)
    valeur_cadastrale = Column(Float, nullable=True)
    etat_bien = Column(String(50), nullable=True)
    zone_geographique = Column(String(100), nullable=True)
    ratio_pret_valeur = Column(Float, nullable=True)
    
    # Decision
    decision = Column(SQLEnum(Decision), nullable=True)
    raison_decision = Column(String(1000), nullable=True)
    score_global = Column(Float, nullable=True)
    taux_interet_propose = Column(Float, nullable=True)
    conditions_supplementaires = Column(String(1000), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<DemandeDB(id='{self.id}', client_id='{self.client_id}', statut='{self.statut}')>"


class ProcessedMessageDB(Base):
    """
    Idempotency tracking - stores processed message IDs
    """
    __tablename__ = "processed_messages"
    __table_args__ = {'extend_existing': True}
    
    # Correlation ID as primary key (ensures uniqueness)
    correlation_id = Column(String(255), primary_key=True)
    
    # Message details
    event_type = Column(String(100), nullable=False)
    demande_id = Column(String(50), nullable=False, index=True)
    
    # Processing metadata
    processed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    processor_service = Column(String(100), nullable=False)
    
    def __repr__(self):
        return f"<ProcessedMessageDB(correlation_id='{self.correlation_id}', event_type='{self.event_type}')>"


class SagaStateDB(Base):
    """
    Saga state persistence for distributed transactions
    """
    __tablename__ = "saga_states"
    __table_args__ = {'extend_existing': True}
    
    # Saga ID as primary key
    saga_id = Column(String(100), primary_key=True)
    
    # Saga details
    demande_id = Column(String(50), nullable=False, index=True)
    current_step_index = Column(Integer, nullable=False, default=0)
    total_steps = Column(Integer, nullable=False)
    
    # State flags
    completed = Column(Boolean, nullable=False, default=False)
    failed = Column(Boolean, nullable=False, default=False)
    compensated = Column(Boolean, nullable=False, default=False)
    
    # Step tracking (JSON-serialized list of step names and states)
    steps_data = Column(String(2000), nullable=True)  # JSON string
    
    # Failure information
    failed_step_name = Column(String(200), nullable=True)
    failure_reason = Column(String(1000), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<SagaStateDB(saga_id='{self.saga_id}', demande_id='{self.demande_id}', completed={self.completed})>"
