"""
Configuration et utilitaires RabbitMQ pour la communication asynchrone
"""
import json
import asyncio
import logging
from typing import Callable, Any, Dict
from aio_pika import connect_robust, Message, ExchangeType
from aio_pika.abc import AbstractRobustConnection, AbstractChannel, AbstractQueue
from shared.events import Event, create_event

logger = logging.getLogger(__name__)


class RabbitMQClient:
    """Client RabbitMQ pour publier et consommer des événements"""
    
    def __init__(self, host: str = "localhost", port: int = 5672, 
                 user: str = "guest", password: str = "guest"):
        """
        Initialise le client RabbitMQ
        
        Args:
            host: Hôte RabbitMQ
            port: Port RabbitMQ
            user: Nom d'utilisateur
            password: Mot de passe
        """
        self.url = f"amqp://{user}:{password}@{host}:{port}/"
        self.connection: AbstractRobustConnection | None = None
        self.channel: AbstractChannel | None = None
        self.exchange_name = "pret_immobilier_events"
        
    async def connect(self):
        """Établit la connexion avec RabbitMQ"""
        try:
            self.connection = await connect_robust(self.url)
            self.channel = await self.connection.channel()
            
            # Créer l'exchange topic pour le routage flexible
            self.exchange = await self.channel.declare_exchange(
                self.exchange_name,
                ExchangeType.TOPIC,
                durable=True
            )
            
            # Créer l'exchange Dead Letter
            self.dlx_exchange = await self.channel.declare_exchange(
                f"{self.exchange_name}.dlx",
                ExchangeType.TOPIC,
                durable=True
            )
            
            logger.info(f"✓ Connecté à RabbitMQ: {self.url}")
            logger.info(f"✓ Exchange DLX créé: {self.exchange_name}.dlx")
        except Exception as e:
            logger.error(f"✗ Erreur de connexion à RabbitMQ: {e}")
            raise
    
    async def disconnect(self):
        """Ferme la connexion avec RabbitMQ"""
        if self.connection:
            await self.connection.close()
            logger.info("✓ Déconnecté de RabbitMQ")
    
    async def publish_event(self, event: Event):
        """
        Publie un événement sur RabbitMQ
        
        Args:
            event: Événement à publier
        """
        if not self.channel:
            raise RuntimeError("Client RabbitMQ non connecté")
        
        try:
            message_body = event.model_dump_json()
            routing_key = event.event_type
            
            message = Message(
                body=message_body.encode(),
                content_type="application/json",
                correlation_id=event.correlation_id,
                headers={
                    "event_type": event.event_type,
                    "demande_id": event.demande_id
                }
            )
            
            await self.exchange.publish(
                message,
                routing_key=routing_key
            )
            
            logger.info(f"📤 Événement publié: {event.event_type} - Demande: {event.demande_id}")
        except Exception as e:
            logger.error(f"✗ Erreur lors de la publication: {e}")
            raise
    
    async def subscribe(self, routing_keys: list[str], queue_name: str, 
                       callback: Callable[[Event], Any],
                       with_dlq: bool = True,
                       max_retries: int = 5,
                       retry_delay_ms: int = 60000):
        """
        S'abonne à des événements spécifiques avec Dead Letter Queue
        
        Args:
            routing_keys: Liste des patterns de routage
            queue_name: Nom de la queue
            callback: Fonction callback asynchrone
            with_dlq: Activer Dead Letter Queue (default: True)
            max_retries: Nombre maximum de tentatives avant DLQ
            retry_delay_ms: Délai de retry en millisecondes
        """
        if not self.channel:
            raise RuntimeError("Client RabbitMQ non connecté")
        
        try:
            # Déclarer la Dead Letter Queue si activée
            dlq_name = f"{queue_name}.dlq"
            retry_queue_name = f"{queue_name}.retry"
            
            if with_dlq:
                # Queue de retry avec TTL
                retry_queue = await self.channel.declare_queue(
                    retry_queue_name,
                    durable=True,
                    arguments={
                        'x-dead-letter-exchange': self.exchange_name,
                        'x-message-ttl': retry_delay_ms,  # Messages expirent et retournent à l'exchange principal
                    }
                )
                
                # Dead Letter Queue finale (après max retries)
                dlq = await self.channel.declare_queue(
                    dlq_name,
                    durable=True
                )
                
                # Lier DLQ à l'exchange DLX
                for routing_key in routing_keys:
                    await dlq.bind(self.dlx_exchange, routing_key=routing_key)
                
                logger.info(f"✓ Dead Letter Queue créée: {dlq_name}")
            
            # Déclarer la queue principale avec DLX
            queue_arguments = {
                'x-dead-letter-exchange': f"{self.exchange_name}.dlx" if with_dlq else None,
            }
            
            queue: AbstractQueue = await self.channel.declare_queue(
                queue_name,
                durable=True,
                arguments={k: v for k, v in queue_arguments.items() if v is not None}
            )
            
            # Lier la queue à l'exchange avec les routing keys
            for routing_key in routing_keys:
                await queue.bind(self.exchange, routing_key=routing_key)
                logger.info(f"📥 Abonné à: {routing_key} sur queue: {queue_name}")
            
            # Consommer les messages
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process(requeue=False):  # Ne pas requeue automatiquement
                        try:
                            # Décoder le message
                            body = json.loads(message.body.decode())
                            event_type = body.get("event_type")
                            demande_id = body.get("demande_id")
                            data = body.get("data", {})
                            correlation_id = body.get("correlation_id", "")
                            
                            # Créer l'événement
                            event = create_event(event_type, demande_id, data, correlation_id)
                            
                            # Vérifier le nombre de retries
                            x_death = message.headers.get('x-death', [])
                            retry_count = 0
                            if x_death and len(x_death) > 0:
                                retry_count = x_death[0].get('count', 0)
                            
                            if retry_count >= max_retries:
                                logger.error(f"✗ Max retries atteint ({retry_count}) pour {event_type}, envoi vers DLQ")
                                # Le message sera automatiquement routé vers DLQ grâce à x-dead-letter-exchange
                                raise Exception(f"Max retries reached: {retry_count}")
                            
                            # Appeler le callback
                            logger.info(f"📨 Événement reçu: {event_type} - Demande: {demande_id} (retry: {retry_count})")
                            await callback(event)
                            
                        except Exception as e:
                            logger.error(f"✗ Erreur lors du traitement du message: {e}")
                            # Le message sera automatiquement routé vers retry queue ou DLQ
                            # grâce à process(requeue=False) et x-dead-letter-exchange
                            raise
        except Exception as e:
            logger.error(f"✗ Erreur lors de la souscription: {e}")
            raise


class EventPublisher:
    """Helper pour publier des événements facilement"""
    
    def __init__(self, rabbitmq_client: RabbitMQClient):
        self.client = rabbitmq_client
    
    async def publish(self, event_type: str, demande_id: str, 
                     data: Dict[str, Any], correlation_id: str = ""):
        """
        Publie un événement
        
        Args:
            event_type: Type d'événement
            demande_id: ID de la demande
            data: Données de l'événement
            correlation_id: ID de corrélation
        """
        event = create_event(event_type, demande_id, data, correlation_id)
        await self.client.publish_event(event)


class EventConsumer:
    """Helper pour consommer des événements facilement"""
    
    def __init__(self, rabbitmq_client: RabbitMQClient, queue_name: str):
        self.client = rabbitmq_client
        self.queue_name = queue_name
        self.handlers: Dict[str, Callable] = {}
    
    def register_handler(self, event_type: str, handler: Callable[[Event], Any]):
        """
        Enregistre un handler pour un type d'événement
        
        Args:
            event_type: Type d'événement
            handler: Fonction handler
        """
        self.handlers[event_type] = handler
        logger.info(f"✓ Handler enregistré pour: {event_type}")
    
    async def start(self):
        """Démarre la consommation des événements"""
        routing_keys = list(self.handlers.keys())
        
        async def handle_event(event: Event):
            handler = self.handlers.get(event.event_type)
            if handler:
                await handler(event)
            else:
                logger.warning(f"⚠ Aucun handler pour: {event.event_type}")
        
        await self.client.subscribe(routing_keys, self.queue_name, handle_event)
