# Guide de Démarrage Rapide

## Prérequis

1. **Docker** installé et démarré
2. **Python 3.12+** avec environnement virtuel

## Étapes de Démarrage

### 1. Démarrer les Services Docker

```bash
# Lancer tous les services (première fois - télécharge les images)
docker compose up -d --build

# Attendre que tous les services soient prêts (environ 30-60 secondes)
# Vérifier l'état des services
docker compose ps
```

**Sortie attendue:**
```
NAME                        STATUS              PORTS
pret_postgres              running             0.0.0.0:5432->5432/tcp
pret_rabbitmq              running             0.0.0.0:5672->5672/tcp, 0.0.0.0:15672->15672/tcp
service_credit             running             0.0.0.0:8002->8002/tcp
service_decision           running             0.0.0.0:8004->8004/tcp
service_demandes           running             0.0.0.0:8001->8001/tcp
service_evaluation_bien    running             0.0.0.0:8003->8003/tcp
service_notification       running             0.0.0.0:8005->8005/tcp
```

### 2. Vérifier que les Services Répondent

```bash
# Vérifier chaque service
curl http://localhost:8001/health  # Service Demandes
curl http://localhost:8002/health  # Service Crédit
curl http://localhost:8003/health  # Service Évaluation
curl http://localhost:8004/health  # Service Décision
curl http://localhost:8005/health  # Service Notification
```

### 3. Configurer l'Environnement Python pour les Tests

```bash
# Créer et activer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances de test
pip install aiohttp
```

### 4. Tester le Système

```bash
# Lancer les tests interactifs
python test_system.py

# Choisir l'option 1 pour vérifier que tous les services sont disponibles
# Puis essayer l'option 2 ou 3 pour tester le flux complet
```

### 5. Créer une Demande Manuellement

```bash
curl -X POST http://localhost:8001/demandes \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "CLIENT001",
    "montant_demande": 250000,
    "revenu_annuel": 60000,
    "duree_pret_mois": 240,
    "adresse_bien": "123 Rue Example, 75001 Paris"
  }'
```

## ### Commandes Utiles

### Voir les logs en temps réel
```bash
# Tous les services
docker compose logs -f

# Un service spécifique
docker compose logs -f service-demandes
docker compose logs -f service-credit
```

### Redémarrer un service
```bash
docker compose restart service-demandes
```

### Arrêter tous les services
```bash
docker compose down
```

### Nettoyer complètement (images + volumes)
```bash
docker compose down -v
docker system prune -a
```

## ### Dépannage

### Problème: "Cannot connect to host localhost:8001"

**Cause:** Les services Docker ne sont pas démarrés ou pas encore prêts.

**Solution:**
```bash
# Vérifier que Docker tourne
docker ps

# Si aucun container, démarrer
docker compose up -d

# Attendre 30 secondes puis vérifier
sleep 30
docker compose ps
```

### Problème: Services en état "Exited" ou "Restarting"

**Cause:** Erreur de démarrage d'un service.

**Solution:**
```bash
# Voir les logs d'erreur
docker compose logs service-demandes
docker compose logs rabbitmq

# Redémarrer
docker compose restart
```

### Problème: Port déjà utilisé

**Cause:** Un autre processus utilise les ports 8001-8005, 5672, ou 15672.

**Solution:**
```bash
# Trouver le processus qui utilise le port
sudo lsof -i :8001

# Tuer le processus ou changer les ports dans docker-compose.yml
```

### Problème: "ModuleNotFoundError: No module named 'aiohttp'"

**Cause:** Les dépendances Python ne sont pas installées.

**Solution:**
```bash
source venv/bin/activate
pip install aiohttp
```

##  Accès aux Interfaces

- **Service Demandes**: http://localhost:8001/docs (Swagger UI)
- **Service Crédit**: http://localhost:8002/docs
- **Service Évaluation**: http://localhost:8003/docs
- **Service Décision**: http://localhost:8004/docs
- **Service Notification**: http://localhost:8005/docs
- **RabbitMQ Management**: http://localhost:15672 (login: guest/guest)

## ### Flux de Test Recommandé

1. **Vérifier les services** (option 1 du test)
2. Si tous sont , **tester une demande simple** (option 2)
3. Puis **tester plusieurs profils** (option 3) pour voir les différentes décisions

## NOTE: Note Importante

WARNING: **Première exécution**: Le téléchargement des images Docker (Python, RabbitMQ, PostgreSQL) peut prendre 5-10 minutes selon votre connexion internet.

 **Exécutions suivantes**: Le démarrage est quasi instantané (5-10 secondes).
