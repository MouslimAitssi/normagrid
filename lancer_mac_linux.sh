#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  NormaGrid - Installation et lancement"
echo "============================================"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERREUR: python3 n'est pas installe."
    echo "Installez Python depuis https://www.python.org/downloads/ ou via votre gestionnaire de paquets."
    exit 1
fi

echo "Installation des dependances (Flask, pywebview)..."
python3 -m pip install -r requirements.txt 2>/dev/null || python3 -m pip install -r requirements.txt --break-system-packages

echo ""
echo "Verification qu'aucun ancien serveur n'occupe deja le port 5000..."
if command -v lsof >/dev/null 2>&1; then
    OLD_PID=$(lsof -ti:5000 2>/dev/null || true)
    if [ -n "$OLD_PID" ]; then
        echo "Arret de l'ancien processus (PID $OLD_PID)..."
        kill -9 $OLD_PID 2>/dev/null || true
        sleep 1
    fi
fi

echo ""
echo "Demarrage de NormaGrid (fenetre native)..."
echo "Une fenetre d'application va s'ouvrir. Fermez-la pour quitter."
echo ""

python3 desktop.py
