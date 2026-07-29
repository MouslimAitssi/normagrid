# NormaGrid - Prototype de saisie (SQLite, multi-projets)

Prototype fonctionnel suivant l'architecture deja definie (Flask + HTML/CSS/JS
vanilla servi par templates/static). Chaque **projet est un fichier .db
independant** (dossier `projects/`), a la maniere d'un fichier bureautique
(Nouveau / Ouvrir / Fermer / Importer).

## Structure

```
normagrid_proto/
├── app.py                     # Point d'entree Flask
├── requirements.txt
├── database/
│   ├── schema.sql              # DDL (tables + FK), utilise pour chaque nouveau projet
│   └── current_project.json    # Nom du fichier-projet actuellement ouvert
├── projects/                   # Un fichier .db par projet (cree a la demande)
├── backend/
│   ├── db.py                    # Gestion multi-projets (creer/ouvrir/fermer/importer)
│   ├── models.py                # Config des tables (source unique) + CRUD generique
│   └── routes/
│       ├── api.py               # Routes /api/... (GET/POST/PUT/DELETE generiques)
│       └── projects.py          # Routes /api/projects/... (gestion des fichiers-projets)
├── static/
│   ├── css/style.css
│   └── js/
│       ├── api.js               # Wrapper fetch() vers l'API
│       └── app.js               # Onglets, arbre, modales, formulaires dynamiques
└── templates/
    └── index.html               # Page unique (bandeau fichiers + 4 onglets + modales)
```

## Lancer le prototype

- **Windows** : double-cliquez sur `lancer_windows.bat`
- **Mac / Linux** : `./lancer_mac_linux.sh`

Au premier lancement, un projet "Default" est cree automatiquement. L'application
s'ouvre desormais dans une **fenetre native** (via `pywebview`), pas un onglet
de navigateur : cela permet les vrais boutons "Parcourir..." (dossier/fichier)
avec l'explorateur natif du systeme, ce qu'une page web classique ne peut pas
faire pour des raisons de securite du navigateur (impossible de revenir a un
chemin reel du disque depuis une simple page web).

**Prerequis natifs (installes automatiquement par pip dans la plupart des cas) :**
- Windows : necessite le runtime **Microsoft Edge WebView2** (deja present sur
  la plupart des Windows 10/11 recents ; sinon telechargeable sur le site de Microsoft)
- Mac : necessite `pyobjc` (installe automatiquement avec pywebview)
- Linux : necessite les bibliotheques systeme GTK+WebKit2 (`sudo apt install
  gir1.2-webkit2-4.1` ou equivalent selon la distribution) ou Qt (`pip install
  pywebview[qt]`)
- **Import Caneco uniquement** : necessite `pdftotext` (poppler-utils), un
  outil systeme (pas une librairie Python) :
  - Windows : binaires poppler (ex. via `conda install poppler` ou `choco
    install poppler`), a ajouter au PATH
  - Mac : `brew install poppler`
  - Linux : `sudo apt install poppler-utils`
  Sans cet outil, tous les autres onglets fonctionnent normalement ; seul
  l'import Caneco affichera un message d'erreur explicite.

Si la fenetre native ne demarre pas (bibliotheque manquante), vous pouvez
toujours lancer le mode navigateur classique en secours :
```bash
python3 app.py
```
puis ouvrir manuellement http://127.0.0.1:5000 (les boutons "Parcourir..."
seront alors desactives, avec la saisie manuelle du chemin en remplacement).

## Gestion des projets (bandeau du haut)

- **Nouveau** : cree un projet vierge (nom + dossier de destination, **obligatoire**, avec bouton "Parcourir..." natif) et l'ouvre
- **Ouvrir** : liste tous les projets connus, ou choisissez un fichier .db via "Parcourir..." (ou collez son chemin)
- **Enregistrer sous** : duplique le projet actuellement ouvert vers un nouveau fichier (nom + dossier obligatoire), qui devient actif
- **Fermer** : ferme le projet actif (retour a l'ecran d'accueil) ; tout est
  deja sauvegarde en continu dans le fichier .db, aucune perte possible
- **Importer** : desactive tant qu'aucun projet n'est ouvert
  - **Ancienne version de NormaGrid** : recuperez un fichier .db d'une version precedente, il devient un nouveau projet
  - **Note de calcul Caneco** : import reel d'un export PDF Caneco BT (ALPI).
    Necessite qu'au moins un reseau HT existe deja dans le projet (choisi
    comme point de rattachement des tableaux racines). Reconstruit
    automatiquement la hierarchie amont/aval, cree les tableaux/transfos/
    groupes electrogenes, un cable par circuit (avec protection quand
    disponible), et les charges terminales. Voir `backend/caneco_import.py`
    pour la methodologie detaillee et ses limites connues.
  - **Excel / Etap** : entrees de menu prevues, le traitement reel sera developpe dans une prochaine etape

## Liste des equipements : edition, suppression et ajout par glisser-depose

- **Double-clic** sur une ligne : ouvre une fenetre d'edition (Sauvegarder / Annuler)
- Bouton **Supprimer** visible sur chaque ligne
- **Palette a droite** : glissez un type d'equipement vers un site ou un
  equipement de l'arbre a gauche pour en creer un nouveau. Le site et
  l'amont sont renseignes automatiquement d'apres la cible du depot (pour
  un tableau avec plusieurs amonts, une ligne est ajoutee dans la table de
  jointure).

## Fonctionnement general

- Un onglet par table dans "Saisie des donnees" ; formulaires generes
  automatiquement depuis `backend/models.py` (`GET /api/schema`).
- Quand vous ajoutez un equipement, une ligne est automatiquement
  creee/mise a jour dans le registre `tag` (unicite garantie).
- Le **Synoptique** reconstruit le schema unifilaire a partir des relations
  amont/aval saisies (aucune action supplementaire necessaire).

## Prochaines etapes (deja anticipees dans l'architecture)

- Traitement reel des imports Excel / Caneco / Etap
- Remplacer `backend/db.py` par une connexion `pyodbc` (Access) ou
  `psycopg2` (PostgreSQL) si un usage multi-utilisateurs est necessaire
- Bilan de puissance (calcul des puissances installees / foisonnees)


## Suite de tests automatiques

Un script de test end-to-end est fourni (`test_normagrid_e2e.py`), qui verifie
automatiquement les fonctionnalites principales via un navigateur pilote
(Playwright). Voir le document "Plan de test automatique NormaGrid" pour le
detail de la couverture. Lancement :

```bash
pip install playwright --break-system-packages
playwright install chromium
python3 test_normagrid_e2e.py --caneco-pdf /chemin/vers/fichier.pdf
```
