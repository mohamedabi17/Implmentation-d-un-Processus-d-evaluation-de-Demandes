"""
Modèles de données partagés entre les services
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


class StatutDemande(str, Enum):
    """Statuts possibles d'une demande de prêt"""
    EN_ATTENTE = "EN_ATTENTE"
    VERIFICATION_CREDIT = "VERIFICATION_CREDIT"
    EVALUATION_BIEN = "EVALUATION_BIEN"
    EN_DECISION = "EN_DECISION"
    APPROUVE = "APPROUVE"
    REJETE = "REJETE"
    ECHEC = "ECHEC"
    ANNULE = "ANNULE"


class Decision(str, Enum):
    """Décisions possibles"""
    APPROUVE = "APPROUVE"
    REJETE = "REJETE"
    ETUDE = "ETUDE"


class DemandeCreate(BaseModel):
    """Modèle pour créer une demande de prêt"""
    client_id: str = Field(..., description="Identifiant unique du client")
    montant_demande: float = Field(..., gt=0, description="Montant du prêt demandé en euros")
    revenu_annuel: float = Field(..., gt=0, description="Revenu annuel du client")
    duree_pret_mois: int = Field(..., gt=0, le=360, description="Durée du prêt en mois")
    adresse_bien: str = Field(..., description="Adresse du bien immobilier")


class Demande(DemandeCreate):
    """Modèle complet d'une demande de prêt"""
    id: str
    statut: StatutDemande = StatutDemande.EN_ATTENTE
    score_credit: Optional[int] = None
    valeur_bien: Optional[float] = None
    decision: Optional[Decision] = None
    raison_decision: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class EvaluationCredit(BaseModel):
    """Résultat de l'évaluation crédit"""
    demande_id: str
    score_credit: int = Field(..., ge=300, le=850, description="Score de crédit FICO")
    antecedents_positifs: bool
    dettes_existantes: float = Field(default=0.0, ge=0)
    ratio_dette_revenu: float = Field(..., ge=0, le=100)


class EvaluationBien(BaseModel):
    """Résultat de l'évaluation du bien"""
    demande_id: str
    valeur_estimee: float = Field(..., gt=0, description="Valeur estimée du bien")
    valeur_cadastrale: float = Field(..., gt=0)
    etat_bien: str = Field(..., description="État du bien (Excellent, Bon, Moyen, Mauvais)")
    zone_geographique: str
    ratio_pret_valeur: float = Field(..., description="LTV - Loan to Value ratio")


class ResultatDecision(BaseModel):
    """Résultat de la décision finale"""
    demande_id: str
    decision: Decision
    raison: str
    score_global: float = Field(..., ge=0, le=100)
    conditions_supplementaires: Optional[str] = None
    taux_interet_propose: Optional[float] = None


class NotificationMessage(BaseModel):
    """Message de notification"""
    demande_id: str
    type: str = Field(..., description="Type de notification")
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Optional[dict] = None


class CompensationEvent(BaseModel):
    """Événement de compensation pour le Saga pattern"""
    demande_id: str
    etape_echec: str
    raison: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
