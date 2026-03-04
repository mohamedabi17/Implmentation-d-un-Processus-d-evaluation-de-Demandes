#!/bin/bash

# Script d'arrêt du système

echo "🛑 Arrêt du système de gestion des prêts..."
docker-compose down

if [ "$1" == "clean" ]; then
    echo "🧹 Nettoyage des volumes..."
    docker-compose down -v
fi

echo "✓ Système arrêté"
