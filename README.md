<div align="center">

# 🏦 Event-Driven Mortgage Approval Platform

**A distributed, fault-tolerant loan-evaluation system built on microservices, the Saga pattern and DMN decision rules.**

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3-FF6600?logo=rabbitmq&logoColor=white)](https://www.rabbitmq.com/)
[![Celery](https://img.shields.io/badge/Celery-5.3-37814A?logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker%20Compose-ready-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)

*Master's project — Business Process Management (TD3)*

</div>

---

## 📌 Table of contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Business process](#-business-process)
- [Saga & compensation](#-saga--compensation)
- [DMN decision table](#-dmn-decision-table)
- [Services & API](#-services--api)
- [Quick start](#-quick-start)
- [Project structure](#-project-structure)

---

## 🎯 Overview

A customer submits a mortgage application; five independent services cooperate through **event choreography** on RabbitMQ — no central orchestrator — to assess the applicant's credit, appraise the property, apply a **DMN decision table**, and notify the customer **in real time** over WebSocket/SSE.

Distributed consistency is guaranteed by a **choreographed Saga** with business compensation: if any step fails, previously completed steps are undone automatically.

| | Guarantee | How |
|---|---|---|
| 🔀 | **Loose coupling** | Each service owns its data; communication only through domain events |
| ⚡ | **Async workers** | CPU/IO-heavy evaluations offloaded to horizontally scalable Celery workers |
| ♻️ | **Consistency** | Saga pattern (in-memory + persistent orchestrator) with compensations |
| 🛡️ | **Fault tolerance** | Manual ACK, retries, dead-letter queues, idempotent handlers |
| 📡 | **Real-time** | WebSocket & Server-Sent Events per application |
| 🔭 | **Observability** | RabbitMQ management UI, Flower dashboard, health endpoints |

---

## 🏗️ Architecture

```mermaid
flowchart TB
    C(["👤 Client"]) -->|REST| D["📝 Demandes service<br/>:8000"]
    C <-->|WebSocket / SSE| N["🔔 Notification service<br/>:8004"]

    D --> PG[("🐘 PostgreSQL")]
    D <-->|events| MQ{{"🐇 RabbitMQ<br/>topic exchange"}}

    MQ <--> CR["💳 Credit service<br/>:8001"]
    MQ <--> BI["🏠 Property service<br/>:8002"]
    MQ <--> DE["⚖️ Decision service<br/>:8003<br/>DMN engine"]
    MQ --> N

    CR -.->|tasks| WC["⚙️ Celery worker<br/>credit"]
    BI -.->|tasks| WB["⚙️ Celery worker<br/>property"]
    WC <--> RD[("🧠 Redis<br/>result backend")]
    WB <--> RD

    FL["🌸 Flower :5555"] -.-> RD

    style MQ fill:#FF6600,color:#fff
    style DE fill:#6B4FBB,color:#fff
```

---

## 🔄 Business process

```mermaid
sequenceDiagram
    autonumber
    actor U as Customer
    participant D as Demandes
    participant MQ as RabbitMQ
    participant C as Credit (+worker)
    participant B as Property (+worker)
    participant X as Decision (DMN)
    participant N as Notification

    U->>D: POST /demandes
    D->>MQ: demande.created
    MQ->>C: demande.created
    C->>C: Celery task: credit score (300-850), DTI
    C-->>MQ: credit.evaluated
    MQ->>B: credit.evaluated
    B->>B: Celery task: appraisal, LTV
    B-->>MQ: bien.evaluated
    MQ->>X: bien.evaluated
    X->>X: DMN table + interest rate
    X-->>MQ: decision.made (APPROUVE / ETUDE / REJETE)
    MQ->>D: update status (each step)
    MQ->>N: every domain event
    N-->>U: real-time push (WebSocket / SSE)
```

### Application state machine

```mermaid
stateDiagram-v2
    [*] --> EN_ATTENTE : POST /demandes
    EN_ATTENTE --> VERIFICATION_CREDIT
    VERIFICATION_CREDIT --> EVALUATION_BIEN : credit.evaluated
    EVALUATION_BIEN --> EN_DECISION : bien.evaluated
    EN_DECISION --> APPROUVE : decision.made
    EN_DECISION --> REJETE : decision.made
    VERIFICATION_CREDIT --> ECHEC : evaluation failed
    EVALUATION_BIEN --> ECHEC : evaluation failed
    ECHEC --> ANNULE : compensation.completed
    APPROUVE --> [*]
    REJETE --> [*]
    ANNULE --> [*]
```

---

## ♻️ Saga & compensation

Each step registers an **execute** and a **compensate** action. On failure the orchestrator runs compensations in **reverse order**.

```mermaid
flowchart LR
    S1["1 · Credit<br/>evaluation"] --> S2["2 · Property<br/>appraisal"] --> S3["3 · Decision"]
    S3 -- ✔ --> OK(["✅ Completed"])
    S3 -. ✖ failure .-> K3["↩ cancel decision"]
    S2 -. ✖ failure .-> K2["↩ bien.cancelled"]
    K3 -.-> K2 -.-> K1["↩ credit.cancelled"] -.-> KO(["🧯 compensation.completed"])
```

Event catalogue (`shared/events.py`):

`demande.created` · `demande.updated` · `credit.evaluation.requested` · `credit.evaluated` · `credit.evaluation.failed` · `bien.evaluation.requested` · `bien.evaluated` · `bien.evaluation.failed` · `decision.requested` · `decision.made` · `compensation.triggered` · `compensation.completed` · `credit.cancelled` · `bien.cancelled` · `notification.sent`

---

## ⚖️ DMN decision table

A weighted score (0–100) is computed from four criteria, then a decision table is applied:

| Criterion | Max points | Best band |
|---|:---:|---|
| Credit score | 35 | ≥ 750 |
| Income / amount ratio | 25 | ≥ 5× |
| Debt-to-income (DTI) | 20 | ≤ 25 % |
| Loan-to-value (LTV) | 20 | ≤ 70 % |

```mermaid
flowchart TD
    A{"Credit ≥ 700<br/>DTI ≤ 40 %<br/>LTV ≤ 90 %"} -- yes --> A1{"score ≥ 75"}
    A1 -- yes --> AP["✅ APPROUVE"]
    A1 -- no --> ET["⚠️ ETUDE"]
    A -- no --> B{"Credit ≥ 650<br/>DTI ≤ 35 %<br/>LTV ≤ 85 %"}
    B -- yes --> B1{"score ≥ 70"}
    B1 -- yes --> AP2["✅ APPROUVE<br/>with conditions"]
    B1 -- no --> ET
    B -- no --> Cc{"Credit ≥ 600<br/>DTI ≤ 30 %<br/>LTV ≤ 80 %"}
    Cc -- yes --> C1{"score ≥ 60"}
    C1 -- yes --> ET
    C1 -- no --> RJ["❌ REJETE"]
    Cc -- no --> RJ
```

The interest rate is then derived from the risk profile (credit score × LTV).

---

## 🔌 Services & API

| Service | Port | Key endpoints |
|---|:---:|---|
| **Demandes** | 8000 | `POST /demandes` · `GET /demandes` · `GET /demandes/{id}` · `PUT /demandes/{id}/statut` · `DELETE /demandes/{id}` |
| **Credit** | 8001 | `POST /credit/evaluer` · `GET /credit/task/{task_id}` |
| **Property** | 8002 | `POST /bien/evaluer` · `GET /bien/task/{task_id}` |
| **Decision** | 8003 | `POST /decision/evaluer` · `GET /decision/regles` |
| **Notification** | 8004 | `WS /ws/{demande_id}` · `GET /sse/{demande_id}` · `POST /notifications/send` |
| RabbitMQ UI | 15672 | management console |
| Flower | 5555 | Celery monitoring |

Every service exposes `GET /health` and interactive docs at `/docs` (Swagger).

---

## 🚀 Quick start

```bash
git clone https://github.com/mohamedabi17/Implmentation-d-un-Processus-d-evaluation-de-Demandes.git
cd Implmentation-d-un-Processus-d-evaluation-de-Demandes

./start.sh            # docker compose up --build -d  (RabbitMQ, Redis, Postgres, 5 services, 2 workers, Flower)
```

Submit an application:

```bash
curl -X POST http://localhost:8000/demandes \
  -H "Content-Type: application/json" \
  -d '{"client_id":"C-001","montant_demande":200000,"revenu_annuel":65000,"duree_pret_mois":240,"adresse_bien":"12 rue de la Paix, Paris"}'
```

Follow it live:

```bash
websocat ws://localhost:8004/ws/<demande_id>
```

Stop everything with `./stop.sh`.

---

## 📁 Project structure

```
.
├── services/
│   ├── demandes/          # API gateway of the process, PostgreSQL repository, event consumer
│   ├── credit/            # FastAPI + Celery tasks (credit scoring)
│   ├── evaluation_bien/   # FastAPI + Celery tasks (property appraisal, LTV)
│   ├── decision/          # DMN rules engine, interest-rate computation
│   └── notification/      # WebSocket / SSE / e-mail simulation
├── shared/
│   ├── events.py          # Typed domain events (Pydantic)
│   ├── rabbitmq.py        # Async publisher / consumer (aio-pika)
│   ├── saga.py            # Saga orchestrator + compensation
│   └── saga_persistent.py # Saga state persisted for crash recovery
├── docker-compose.yml
├── start.sh / stop.sh
└── rapport.tex            # Full technical report
```

---

<div align="center">

**Mohamed Abi** · [GitHub @mohamedabi17](https://github.com/mohamedabi17)

</div>
