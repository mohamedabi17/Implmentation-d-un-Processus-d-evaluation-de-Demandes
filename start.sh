#!/bin/bash

# Script de démarrage du système de gestion des prêts immobiliers

echo "=================================="
echo "Système de Gestion des Prêts"
echo "=================================="
echo ""

# Vérifier que Docker est installé
if ! command -v docker &> /dev/null; then
    echo "✗ Docker n'est pas installé"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "✗ Docker Compose n'est pas installé"
    exit 1
fi

echo "✓ Docker et Docker Compose sont installés"
echo ""

# Nettoyer les anciens containers si demandé
if [ "$1" == "clean" ]; then
    echo "🧹 Nettoyage des anciens containers..."
    docker-compose down -v
    echo ""
fi

# Construire les images
echo "🔨 Construction des images Docker..."
docker-compose build

if [ $? -ne 0 ]; then
    echo "✗ Erreur lors de la construction"
    exit 1
fi

echo ""
echo "✓ Images construites avec succès"
echo ""

# Démarrer les services
echo "🚀 Démarrage des services..."
docker-compose up -d

if [ $? -ne 0 ]; then
    echo "✗ Erreur lors du démarrage"
    exit 1
fi

echo ""
echo "⏳ Attente du démarrage complet (30 secondes)..."
sleep 30

# Vérifier le statut des services
echo ""
echo "📊 Statut des services:"
echo ""
docker-compose ps

echo ""
echo "=================================="
echo "✓ Système démarré avec succès!"
echo "=================================="
echo ""
echo "URLs des services:"
echo "  - Service Demandes:      http://localhost:8001"
echo "  - Service Crédit:        http://localhost:8002"
echo "  - Service Évaluation:    http://localhost:8003"
echo "  - Service Décision:      http://localhost:8004"
echo "  - Service Notification:  http://localhost:8005"
echo "  - RabbitMQ Management:   http://localhost:15672 (guest/guest)"
echo ""
echo "Pour voir les logs:"
echo "  docker-compose logs -f [service_name]"
echo ""
echo "Pour arrêter le système:"
echo "  docker-compose down"
echo ""
echo "Pour tester le système:"
echo "  python test_system.py"
echo ""
