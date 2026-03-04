"""
Définition des événements pour la communication entre microservices
"""
from typing import Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field


class Event(BaseModel):
    """Classe de base pour tous les événements"""
    event_type: str
    demande_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = {}
    correlation_id: str = ""


# Événements du Service Demandes
class DemandeCreatedEvent(Event):
    """Événement déclenché lors de la création d'une demande"""
    event_type: str = "demande.created"


class DemandeUpdatedEvent(Event):
    """Événement déclenché lors de la mise à jour d'une demande"""
    event_type: str = "demande.updated"


# Événements du Service Crédit
class CreditEvaluationRequestedEvent(Event):
    """Événement pour demander une évaluation de crédit"""
    event_type: str = "credit.evaluation.requested"


class CreditEvaluatedEvent(Event):
    """Événement déclenché après l'évaluation du crédit"""
    event_type: str = "credit.evaluated"


class CreditEvaluationFailedEvent(Event):
    """Événement déclenché si l'évaluation crédit échoue"""
    event_type: str = "credit.evaluation.failed"


# Événements du Service Évaluation Bien
class BienEvaluationRequestedEvent(Event):
    """Événement pour demander une évaluation du bien"""
    event_type: str = "bien.evaluation.requested"


class BienEvaluatedEvent(Event):
    """Événement déclenché après l'évaluation du bien"""
    event_type: str = "bien.evaluated"


class BienEvaluationFailedEvent(Event):
    """Événement déclenché si l'évaluation du bien échoue"""
    event_type: str = "bien.evaluation.failed"


# Événements du Service Décision
class DecisionRequestedEvent(Event):
    """Événement pour demander une décision"""
    event_type: str = "decision.requested"


class DecisionMadeEvent(Event):
    """Événement déclenché après la prise de décision"""
    event_type: str = "decision.made"


# Événements de Compensation (Saga Pattern)
class CompensationTriggeredEvent(Event):
    """Événement déclenché pour initier une compensation"""
    event_type: str = "compensation.triggered"


class CompensationCompletedEvent(Event):
    """Événement déclenché après la compensation"""
    event_type: str = "compensation.completed"


# Événements de Notification
class NotificationSentEvent(Event):
    """Événement déclenché après l'envoi d'une notification"""
    event_type: str = "notification.sent"


# Événements de compensation spécifiques (Saga Pattern)
class CreditCancelledEvent(Event):
    """Événement déclenché quand le crédit est annulé (compensation)"""
    event_type: str = "credit.cancelled"


class BienCancelledEvent(Event):
    """Événement déclenché quand l'évaluation bien est annulée (compensation)"""
    event_type: str = "bien.cancelled"


# Mapping des types d'événements vers leurs classes
EVENT_TYPES = {
    "demande.created": DemandeCreatedEvent,
    "demande.updated": DemandeUpdatedEvent,
    "credit.evaluation.requested": CreditEvaluationRequestedEvent,
    "credit.evaluated": CreditEvaluatedEvent,
    "credit.evaluation.failed": CreditEvaluationFailedEvent,
    "bien.evaluation.requested": BienEvaluationRequestedEvent,
    "bien.evaluated": BienEvaluatedEvent,
    "bien.evaluation.failed": BienEvaluationFailedEvent,
    "decision.requested": DecisionRequestedEvent,
    "decision.made": DecisionMadeEvent,
    "compensation.triggered": CompensationTriggeredEvent,
    "compensation.completed": CompensationCompletedEvent,
    "credit.cancelled": CreditCancelledEvent,
    "bien.cancelled": BienCancelledEvent,
    "notification.sent": NotificationSentEvent,
}


def create_event(event_type: str, demande_id: str, data: Dict[str, Any], correlation_id: str = "") -> Event:
    """
    Factory pour créer un événement du bon type
    
    Args:
        event_type: Type d'événement
        demande_id: ID de la demande concernée
        data: Données de l'événement
        correlation_id: ID de corrélation pour le traçage
        
    Returns:
        Instance de l'événement approprié
    """
    event_class = EVENT_TYPES.get(event_type, Event)
    return event_class(
        event_type=event_type,
        demande_id=demande_id,
        data=data,
        correlation_id=correlation_id or demande_id
    )
