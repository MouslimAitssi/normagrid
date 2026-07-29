#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  NormaGrid - Suite de tests automatiques"
echo "============================================"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERREUR: python3 n'est pas installe."
    echo "Installez Python depuis https://www.python.org/downloads/ ou via votre gestionnaire de paquets."
    exit 1
fi

echo "Installation de Playwright (necessaire uniquement pour les tests)..."
python3 -m pip install playwright 2>/dev/null || python3 -m pip install playwright --break-system-packages

echo ""
echo "Installation du navigateur Chromium pour les tests (peut prendre 1-2 minutes)..."
python3 -m playwright install chromium

echo ""
echo "============================================"
echo "  Lancement de la suite de tests"
echo "============================================"
echo ""

if [ -n "$1" ]; then
    echo "Fichier Caneco fourni : $1"
    python3 test_normagrid_e2e.py --caneco-pdf "$1"
else
    echo "Astuce : passez un fichier PDF Caneco en argument pour tester aussi"
    echo "l'import Caneco (ex: ./lancer_tests_mac_linux.sh /chemin/vers/fichier.pdf)."
    echo "Sans fichier, ce test est simplement ignore (SKIP), le reste s'execute quand meme."
    echo ""
    python3 test_normagrid_e2e.py
fi

echo ""
echo "============================================"
echo "  Tests termines - voir le rapport ci-dessus"
echo "============================================"
