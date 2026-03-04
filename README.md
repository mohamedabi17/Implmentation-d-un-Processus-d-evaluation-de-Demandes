# Système Microservices d'Évaluation de Prêt Immobilier

Architecture événementielle distribuée pour le traitement automatisé des demandes de prêt immobilier, implémentée avec FastAPI, RabbitMQ, Celery et PostgreSQL.

## Table des Matières

- [Vue d'ensemble](#vue-densemble)
- [Architecture](#architecture)
- [Fonctionnalités](#fonctionnalités)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Démarrage Rapide](#démarrage-rapide)
- [Utilisation](#utilisation)
- [Architecture Technique](#architecture-technique)
- [API Documentation](#api-documentation)
- [Monitoring](#monitoring)
- [Technologies](#technologies)
- [Structure du Projet](#structure-du-projet)
- [Garanties Techniques](#garanties-techniques)

## Vue d'ensemble

Ce projet implémente un système complet de traitement de demandes de prêt immobilier basé sur une architecture microservices événementielle. Le système garantit la cohérence transactionnelle distribuée grâce au Saga Pattern avec compensation métier automatique.

### Caractéristiques Principales

- **Architecture Microservices** : 5 services indépendants avec bases de données isolées
- **Communication Asynchrone** : Événements RabbitMQ avec garantie de livraison
- **Traitement Parallèle** : Workers Celery distribués avec scalabilité horizontale
- **Cohérence Forte** : Idempotence atomique et transactions uniques
- **Saga Pattern** : Compensation métier chorégraphiée (conforme TD3)
- **Tolérance aux Pannes** : Retry automatique, Dead Letter Queues, redelivery
- **Temps Réel** : Notifications WebSocket pour suivi instantané

## Architecture

### Schéma Global

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Client    │────▶│   Service    │────▶│  RabbitMQ   │
│             │     │  Demandes    │     │   Broker    │
└─────────────┘     └──────────────┘     └─────────────┘
                           │                     │
                           ▼                     ▼
                    ┌──────────────┐     ┌─────────────┐
                    │  PostgreSQL  │     │   Service   │
                    │   Database   │     │   Crédit    │
                    └──────────────┘     └─────────────┘
                                                │
                                                ▼
                                         ┌─────────────┐
                                         │   Service   │
                                         │    Bien     │
                                         └─────────────┘
                                                │
                                                ▼
                                         ┌─────────────┐
                                         │   Service   │
                                         │  Décision   │
                                         └─────────────┘
                                                │
                                                ▼
                                         ┌─────────────┐
                                         │   Service   │
                                         │Notification │
                                         └─────────────┘
```

### Microservices

1. **Service Demandes** (Port 8000)
   - Gestion du cycle de vie des demandes
   - Agrégation des résultats
   - API REST principale

2. **Service Crédit** (Port 8001)
   - Évaluation de la solvabilité
   - Calcul du score de crédit
   - Worker Celery asynchrone

3. **Service Évaluation Bien** (Port 8002)
   - Estimation de la valeur immobilière
   - Calcul du ratio LTV (Loan-to-Value)
   - Worker Celery asynchrone

4. **Service Décision** (Port 8003)
   - Application des règles métier DMN
   - Calcul du taux d'intérêt
   - Décision finale automatisée

5. **Service Notification** (Port 8004)
   - Notifications temps réel WebSocket
   - Envoi d'emails (simulation)
   - Server-Sent Events (SSE)

## Fonctionnalités

### Traitement de Demande Complet

1. **Création de demande** via API REST
2. **Évaluation crédit** asynchrone (3-8 secondes)
3. **Évaluation bien** asynchrone (5-10 secondes)
4. **Décision automatisée** selon règles DMN
5. **Notification client** en temps réel

### Saga Pattern avec Compensation

Le système implémente une compensation métier distribuée :

```
Succès :
POST /demandes → Crédit OK → Bien OK → Décision OK → APPROVED

Échec avec compensation :
POST /demandes → Crédit OK → Bien OK → Décision FAIL
  → compensation.triggered
  → credit.cancelled
  → bien.cancelled
  → demande.status = REJECTED
```

### Garanties Transactionnelles

- **Idempotence** : `INSERT ON CONFLICT` atomique sur `correlation_id`
- **Exactly-once** : Transaction unique incluant marquage + update métier
- **Pas de fenêtre de crash** : COMMIT avant ACK message
- **Isolation** : Base de données par service (Database per Service pattern)

## Prérequis

- **Docker** 20.10+ et Docker Compose 2.0+
- **Python** 3.11+ (pour développement local)
- **Git** (pour cloner le dépôt)
- **4 GB RAM minimum** (8 GB recommandé)
- **Ports disponibles** : 5432, 5555, 5672, 6379, 8000-8004, 15672

## Installation

### 1. Cloner le Dépôt

```bash
git clone https://github.com/mohamedabi17/Impl-mentation-d-un-Processus-d-valuation-de-Demandes-de-Pr-t-.git
cd Impl-mentation-d-un-Processus-d-valuation-de-Demandes-de-Pr-t-
```

### 2. Configuration (Optionnelle)

Le fichier `.env` est déjà fourni avec des valeurs par défaut :

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
```

## Démarrage Rapide

### Lancer tous les services

```bash
# Démarrage complet (télécharge les images Docker la première fois)
docker compose up -d --build

# Vérifier que tous les services sont démarrés
docker compose ps
```

**Sortie attendue :**
```
NAME                        STATUS              PORTS
pret_postgres              running             0.0.0.0:5432->5432/tcp
pret_rabbitmq              running             0.0.0.0:5672->5672/tcp, 0.0.0.0:15672->15672/tcp
pret_redis                 running             0.0.0.0:6379->6379/tcp
service_demandes           running             0.0.0.0:8000->8000/tcp
service_credit             running             0.0.0.0:8001->8001/tcp
service_evaluation_bien    running             0.0.0.0:8002->8002/tcp
service_decision           running             0.0.0.0:8003->8003/tcp
service_notification       running             0.0.0.0:8004->8004/tcp
worker_credit              running
worker_evaluation_bien     running
flower_monitoring          running             0.0.0.0:5555->5555/tcp
```

### Créer une Demande de Test

```bash
curl -X POST http://localhost:8000/demandes \
  -H "Content-Type: application/json" \
  -d '{
    "nom_client": "Dupont",
    "prenom_client": "Jean",
    "email_client": "jean.dupont@example.com",
    "montant_demande": 250000,
    "duree_pret_mois": 240,
    "revenu_annuel": 50000,
    "adresse_bien": "15 Rue de la République, 75001 Paris",
    "type_bien": "appartement",
    "valeur_estimee_bien": 300000
  }'
```

**Réponse :**
```json
{
  "demande_id": "DEM-20260304-ABC123",
  "statut": "PENDING",
  "message": "Demande créée avec succès. Évaluation en cours..."
}
```

### Consulter le Statut

```bash
curl http://localhost:8000/demandes/DEM-20260304-ABC123
```

### Arrêter les Services

```bash
# Arrêt propre
docker compose down

# Arrêt + suppression des volumes (reset complet)
docker compose down -v
```

## Utilisation

### API REST Endpoints

#### Service Demandes (8000)

```bash
# Créer une demande
POST /demandes

# Consulter une demande
GET /demandes/{demande_id}

# Lister toutes les demandes
GET /demandes

# Health check
GET /health
```

#### Service Crédit (8001)

```bash
# Lancer évaluation crédit
POST /credit/evaluate/{demande_id}

# Consulter résultat
GET /credit/{demande_id}
```

#### Service Évaluation Bien (8002)

```bash
# Lancer évaluation bien
POST /bien/evaluate/{demande_id}

# Consulter résultat
GET /bien/{demande_id}
```

#### Service Décision (8003)

```bash
# Déclencher décision
POST /decision/process/{demande_id}

# Consulter décision
GET /decision/{demande_id}
```

#### Service Notification (8004)

```bash
# WebSocket temps réel
WS /ws/{demande_id}

# Server-Sent Events
GET /events/{demande_id}
```

### Notifications Temps Réel

#### WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8004/ws/DEM-20260304-ABC123');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Statut:', data.status);
  // Output: PENDING → CREDIT_EVALUATED → BIEN_EVALUATED → APPROVED
};
```

#### Avec `wscat` (CLI)

```bash
npm install -g wscat
wscat -c ws://localhost:8004/ws/DEM-20260304-ABC123
```

## Architecture Technique

### Communication Événementielle

#### Événements Principaux

| Événement | Émetteur | Consommateur | Description |
|-----------|----------|--------------|-------------|
| `credit.evaluated` | Service Crédit | Service Demandes | Résultat évaluation crédit |
| `bien.evaluated` | Service Bien | Service Demandes | Résultat évaluation bien |
| `decision.made` | Service Décision | Service Demandes + Notification | Décision finale |
| `notification.sent` | Service Notification | Service Demandes | Confirmation envoi |

#### Événements de Compensation (Saga Pattern)

| Événement | Émetteur | Consommateur | Action |
|-----------|----------|--------------|--------|
| `compensation.triggered` | Service en échec | Tous les services | Déclenche rollback |
| `credit.cancelled` | Service Crédit | Service Demandes | Annule évaluation crédit |
| `bien.cancelled` | Service Bien | Service Demandes | Annule évaluation bien |

### Configuration RabbitMQ

- **Exchange Type** : TOPIC (routage flexible)
- **Durabilité** : Exchanges et queues durables
- **Persistance** : Messages persistés sur disque
- **TTL Messages** : 24 heures
- **Dead Letter Queue** : Configurée pour tous les types d'événements
- **Acknowledgment** : Mode `acks_late` pour garantir la fiabilité

### Configuration Celery

#### Retry Strategy

```python
max_retries = 5
retry_backoff = True (exponentiel)
retry_backoff_max = 600 secondes
retry_jitter = True (évite synchronisation)
```

**Séquence de retry :**
```
Tentative 1: Immédiate
Tentative 2: +60s
Tentative 3: +120s
Tentative 4: +240s
Tentative 5: +480s
Tentative 6: +600s (max)
→ Dead Letter Queue si échec final
```

#### Scalabilité Horizontale

```bash
# Scaler les workers crédit
docker compose up -d --scale worker_credit=4

# Scaler les workers bien
docker compose up -d --scale worker_evaluation_bien=8
```

## API Documentation

### Swagger UI (Interface Interactive)

Accédez aux documentations Swagger de chaque service :

- **Demandes** : http://localhost:8000/docs
- **Crédit** : http://localhost:8001/docs
- **Bien** : http://localhost:8002/docs
- **Décision** : http://localhost:8003/docs
- **Notification** : http://localhost:8004/docs

### Exemple de Schéma de Demande

```json
{
  "nom_client": "string",
  "prenom_client": "string",
  "email_client": "user@example.com",
  "montant_demande": 250000,
  "duree_pret_mois": 240,
  "revenu_annuel": 50000,
  "adresse_bien": "string",
  "type_bien": "appartement | maison | terrain",
  "valeur_estimee_bien": 300000
}
```

## Monitoring

### RabbitMQ Management UI

Interface de gestion RabbitMQ :

- **URL** : http://localhost:15672
- **Identifiants** : `guest` / `guest`
- **Fonctionnalités** :
  - Visualisation des queues et exchanges
  - Métriques de messages (rates, totaux)
  - Monitoring des consommateurs
  - Dead Letter Queues

### Flower (Monitoring Celery)

Dashboard pour les tâches Celery :

- **URL** : http://localhost:5555
- **Fonctionnalités** :
  - État des workers en temps réel
  - Historique des tâches (succès/échec)
  - Temps d'exécution par tâche
  - Monitoring de la charge

### Logs Docker

```bash
# Tous les services
docker compose logs -f

# Un service spécifique
docker compose logs -f service_demandes

# Avec filtre timestamp
docker compose logs -f --since 10m

# Worker crédit
docker compose logs -f worker_credit
```

## Technologies

### Backend

- **FastAPI** 0.109+ : Framework web asynchrone haute performance
- **SQLAlchemy** 2.0+ : ORM avec support async
- **Pydantic** 2.0+ : Validation de données
- **asyncpg** : Driver PostgreSQL asynchrone

### Messagerie & Workers

- **RabbitMQ** 3.13 : Message broker AMQP
- **Celery** 5.3+ : Distributed task queue
- **Redis** 7.2 : Backend de résultats Celery
- **aio-pika** : Client RabbitMQ asynchrone

### Base de Données

- **PostgreSQL** 15 : Base de données relationnelle
- **Alembic** : Migrations de schéma (optionnel)

### Infrastructure

- **Docker** 24+ : Conteneurisation
- **Docker Compose** 2.0+ : Orchestration multi-conteneurs
- **Uvicorn** : Serveur ASGI

## Structure du Projet

```
.
├── services/
│   ├── demandes/
│   │   ├── main.py              # API REST FastAPI
│   │   ├── database.py          # Configuration SQLAlchemy
│   │   ├── db_models.py         # Modèles de données
│   │   ├── repository.py        # Accès données
│   │   ├── event_consumer.py    # Consommateur RabbitMQ
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── credit/
│   │   ├── main.py              # API REST
│   │   ├── tasks.py             # Tâches Celery
│   │   ├── celery_app.py        # Configuration Celery
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── evaluation_bien/
│   │   ├── main.py
│   │   ├── tasks.py
│   │   ├── celery_app.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── decision/
│   │   ├── main.py
│   │   ├── dmn_rules.py         # Règles métier DMN
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── notification/
│       ├── main.py
│       ├── Dockerfile
│       └── requirements.txt
├── shared/
│   ├── events.py                # Gestion événements
│   ├── models.py                # Modèles partagés
│   ├── rabbitmq.py              # Connexion RabbitMQ
│   ├── saga.py                  # Saga Pattern en mémoire
│   ├── saga_persistent.py       # Saga Pattern persistant
│   └── requirements.txt
├── captures/                    # Screenshots documentation
├── docker-compose.yml           # Orchestration services
├── .env                         # Configuration environnement
├── .gitignore
├── requirements.txt             # Dépendances principales
├── start.sh                     # Script démarrage
├── stop.sh                      # Script arrêt
├── DEMARRAGE.md                 # Guide démarrage
├── rapport.tex                  # Rapport LaTeX académique
└── README.md                    # Ce fichier
```

## Garanties Techniques

### Idempotence Atomique

Tous les handlers d'événements garantissent un traitement exactly-once :

```sql
INSERT INTO processed_messages (correlation_id, ...)
VALUES (...)
ON CONFLICT (correlation_id) DO NOTHING
RETURNING correlation_id;
```

- Si `correlation_id` existe déjà → Message ignoré
- Si `correlation_id` nouveau → Message traité
- **Atomicité garantie** par contrainte PRIMARY KEY PostgreSQL

### Transaction Unique

Toutes les opérations d'un handler sont dans une transaction :

```python
async with session.begin():  # BEGIN
    should_process = await try_mark_as_processed(...)
    if not should_process:
        return  # ROLLBACK automatique
    
    await update_data(...)
    # COMMIT automatique à la sortie
```

**Garanties :**
- Pas de fenêtre de crash entre update et marquage idempotence
- COMMIT avant ACK message RabbitMQ
- ROLLBACK automatique en cas d'exception

### Saga Pattern - Compensation Métier

Implémentation chorégraphiée sans orchestrateur central :

**Scénario : Échec Service Décision**

```
1. POST /demandes → CREATED
2. Service Crédit → credit.evaluated ✓
3. Service Bien → bien.evaluated ✓
4. Service Décision → CRASH ✗
   → Publish: compensation.triggered
   
5. Service Bien reçoit compensation.triggered
   → Publish: bien.cancelled
   
6. Service Crédit reçoit compensation.triggered
   → Publish: credit.cancelled
   
7. Service Demandes reçoit compensation.triggered
   → UPDATE demandes SET statut = 'REJECTED'
   → Raison: "Compensation - prise_decision échouée"

RÉSULTAT: Rollback distribué complet
```

### Tolérance aux Pannes

| Scénario | Mécanisme | Résultat |
|----------|-----------|----------|
| Worker crash avant COMMIT | ROLLBACK auto + Redelivery RabbitMQ | Message retraité |
| Worker crash après COMMIT | ACK non envoyé → Redelivery | Idempotence détecte duplicate |
| Double delivery RabbitMQ | INSERT ON CONFLICT | Deuxième traitement ignoré |
| Network partition | Transaction timeout → ROLLBACK | Message retraité |
| Database unavailable | Retry Celery (5x) → DLQ | Alertes monitoring |

## Performances

### Métriques Typiques

| Métrique | Valeur |
|----------|--------|
| Latence création demande | < 100ms |
| Temps évaluation crédit | 3-8 secondes |
| Temps évaluation bien | 5-10 secondes |
| Temps décision | < 500ms |
| Latence notification | < 200ms |
| **Durée totale E2E** | **10-20 secondes** |

### Scalabilité

- **Horizontal** : Workers Celery (1 à 50+)
- **Vertical** : Ressources PostgreSQL, RabbitMQ
- **Capacité testée** : 100 demandes/seconde
- **Dimensionnement recommandé** :
  - 1 worker pour 100 demandes/jour
  - 4 workers pour 1000 demandes/jour
  - 10+ workers pour charge élevée

## Troubleshooting

### Services ne démarrent pas

```bash
# Vérifier les logs
docker compose logs

# Vérifier les ports
netstat -tuln | grep -E '5432|5672|6379|800[0-4]|15672|5555'

# Redémarrer proprement
docker compose down -v
docker compose up -d --build
```

### Messages bloqués dans RabbitMQ

```bash
# Vérifier les queues via Management UI
http://localhost:15672

# Purger une queue (ATTENTION: perte de données)
docker compose exec rabbitmq rabbitmqadmin purge queue name=credit_evaluation_queue
```

### Base de données corrompue

```bash
# Reset complet (ATTENTION: perte de données)
docker compose down -v
docker volume rm projet_bpm_td3_postgres_data
docker compose up -d
```

### Workers Celery inactifs

```bash
# Vérifier les workers via Flower
http://localhost:5555

# Redémarrer un worker
docker compose restart worker_credit
```

## Développement

### Environnement Local

```bash
# Créer environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Installer dépendances
pip install -r requirements.txt

# Variables d'environnement
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/demandes
export RABBITMQ_URL=amqp://guest:guest@localhost:5672/
export REDIS_URL=redis://localhost:6379/0
```

### Lancer un Service Individuellement

```bash
cd services/demandes
uvicorn main:app --reload --port 8000
```

## Auteurs

- **ABI Mohamed** - Développement et architecture
- **BOUAGADA Youcef** - Développement et tests

## Licence

Ce projet est développé dans le cadre du Master 2 DataScale - Université Paris-Saclay.

---

**Projet académique** - Master 2 Microservices et Architectures Distribuées  
**Année académique** : 2025-2026  
**Institution** : Université Paris-Saclay

Pour plus de détails, consultez le [rapport technique LaTeX](rapport.tex) ou le [guide de démarrage](DEMARRAGE.md).
