"""
============================================================================
NormaGrid - Suite de tests automatiques (end-to-end)
============================================================================

Ce script verifie automatiquement le bon fonctionnement des fonctionnalites
principales de l'application, en pilotant un vrai navigateur (Playwright)
contre un serveur NormaGrid lance localement. Il couvre :

  1. Gestion de projet (creer, ouvrir, enregistrer sous, fermer, import
     bloque sans projet ouvert)
  2. Saisie des donnees / CRUD (creation, edition, suppression)
  3. Arborescence des equipements (avals directs, exclusion cables/charges,
     glisser-depose avec amont automatique)
  4. Import Caneco (precondition reseau HT, apercu des amonts modifiable,
     choix d'importer ou non les charges)
  5. Synoptique (zoom, filtre en arborescence avec decochage en cascade)
  6. Carnet de cables (onglet, filtres par colonne, export Excel)
  7. Export de la base de donnees (script SQL avec relations)

Utilisation :
    pip install playwright --break-system-packages
    playwright install chromium
    python3 test_normagrid_e2e.py [--caneco-pdf /chemin/vers/fichier.pdf]

Le script demarre son propre serveur Flask sur le port 5050 (pour ne pas
entrer en conflit avec une instance deja lancee), execute tous les tests,
affiche un rapport PASS/FAIL detaille, puis s'arrete. Code de sortie 0 si
tout est passe, 1 sinon (utilisable dans un pipeline d'integration continue).
"""

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 5050
BASE_URL = f"http://127.0.0.1:{PORT}"

RESULTS = []  # liste de (nom_du_test, ok: bool, message: str)


def record(name, ok, message=""):
    RESULTS.append((name, ok, message))
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" -- {message}" if message else ""))


class Check:
    """Petit utilitaire pour enchainer des assertions dans un test et
    continuer meme si l'une d'elles echoue, afin de ne pas perdre la
    visibilite sur les suivantes."""

    def __init__(self, test_name):
        self.test_name = test_name
        self.failures = []

    def that(self, condition, description):
        if not condition:
            self.failures.append(description)

    def finish(self):
        if self.failures:
            record(self.test_name, False, "; ".join(self.failures))
        else:
            record(self.test_name, True)


def wait_for_server(url, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


async def api_post(page, path, json_body=None, form_data=None, files=None):
    """Effectue un appel API via fetch() dans la page (reutilise la session)."""
    if files:
        return None  # les uploads de fichiers passent par Playwright set_input_files, pas ici
    body_js = "null" if json_body is None else __import__("json").dumps(json_body)
    return await page.evaluate(
        f"""async () => {{
            const r = await fetch('{path}', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({body_js}),
            }});
            return {{status: r.status, body: await r.json()}};
        }}"""
    )


async def api_get(page, path):
    return await page.evaluate(
        f"""async () => {{
            const r = await fetch('{path}');
            return {{status: r.status, body: await r.json()}};
        }}"""
    )


# ============================================================================
# 1. Gestion de projet
# ============================================================================

async def test_project_management(page, workdir):
    chk = Check("1. Gestion de projet")

    # Nouveau projet avec dossier personnalise (obligatoire)
    custom_folder = os.path.join(workdir, "mes_projets")
    r = await api_post(page, "/api/projects/new", {"name": "ProjetTest", "folder": custom_folder})
    chk.that(r["status"] == 201, f"creation nouveau projet (recu {r['status']}: {r['body']})")
    chk.that(os.path.exists(os.path.join(custom_folder, "ProjetTest.db")),
             "le fichier .db doit exister dans le dossier choisi par l'utilisateur")

    # Enregistrer sous
    r = await api_post(page, "/api/projects/save-as", {"name": "ProjetTest_Copie", "folder": custom_folder})
    chk.that(r["status"] == 201, f"enregistrer sous (recu {r['status']})")
    chk.that(os.path.exists(os.path.join(custom_folder, "ProjetTest_Copie.db")),
             "la copie doit exister apres Enregistrer sous")

    # Import bloque tant qu'aucun projet n'est ouvert
    await api_post(page, "/api/projects/close")
    r = await api_post(page, "/api/projects/import-caneco/analyze")
    chk.that(r["status"] == 409, f"import Caneco doit etre bloque (409) sans projet ouvert (recu {r['status']})")

    # Reouvrir pour la suite des tests
    r = await api_post(page, "/api/projects/open", {"path": os.path.join(custom_folder, "ProjetTest.db")})
    chk.that(r["status"] == 200, "reouverture du projet de test")

    chk.finish()


# ============================================================================
# 2. Saisie des donnees / CRUD
# ============================================================================

async def test_crud(page):
    chk = Check("2. Saisie des donnees (CRUD)")

    steps = [
        ("client", {"tag": "CLIENT1", "nom": "Client Test"}),
        ("projet", {"tag": "PROJET1", "client_tag": "CLIENT1", "nom": "Projet Test"}),
        ("site", {"tag": "SITE1", "client_tag": "PROJET1", "nom": "Site Test"}),
        ("reseau_ht", {"tag_id": "RHT1", "site_id": "SITE1", "nom": "Arrivee", "tension_kv": 20,
                        "pcc_max_mva": 100, "x_r_max": 10, "pcc_min_mva": 50, "x_r_min": 5}),
        ("transfos", {"tag_id": "TR1", "site_id": "SITE1", "amont_id": "RHT1", "puissance_kva": 630}),
        ("tableaux", {"tag_id": "TGBT1", "site_id": "SITE1", "type": "TGBT", "tension_v": 400}),
        ("cable", {"tag_id": "CAB1", "site_id": "SITE1", "amont_id": "TR1", "type": "U1000R2V",
                    "section": "5G10", "longueur_m": 25}),
    ]
    for table, payload in steps:
        r = await api_post(page, f"/api/{table}", payload)
        chk.that(r["status"] == 201, f"creation {table} (recu {r['status']}: {r.get('body')})")

    r = await api_get(page, "/api/tableaux/TGBT1")
    chk.that(r["status"] == 200 and r["body"]["type"] == "TGBT", "lecture d'un equipement cree")

    # Edition (PUT)
    r = await page.evaluate(
        """async () => {
            const r = await fetch('/api/tableaux/TGBT1', {
                method: 'PUT', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({tag_id:'TGBT1', site_id:'SITE1', type:'TGBT modifie', tension_v:400}),
            });
            return {status: r.status, body: await r.json()};
        }"""
    )
    chk.that(r["status"] == 200, f"modification d'un equipement (recu {r['status']})")
    r = await api_get(page, "/api/tableaux/TGBT1")
    chk.that(r["body"]["type"] == "TGBT modifie", "la modification doit etre persistee")

    # Suppression
    r = await page.evaluate(
        """async () => {
            const r = await fetch('/api/cable/CAB1', {method: 'DELETE'});
            return {status: r.status};
        }"""
    )
    chk.that(r["status"] == 200, f"suppression d'un equipement (recu {r['status']})")
    r = await api_get(page, "/api/cable")
    chk.that(all(row["tag_id"] != "CAB1" for row in r["body"]), "l'equipement supprime ne doit plus apparaitre")

    chk.finish()


# ============================================================================
# 3. Arborescence des equipements
# ============================================================================

async def test_tree_and_dragdrop(page):
    chk = Check("3. Arborescence des equipements")

    # Reconstruire un cable + charge pour tester l'exclusion arbre/liste
    # (CAB1 a ete supprime intentionnellement par le test CRUD precedent : on
    # recree le lien TR1 -> TGBT1 necessaire pour tester les avals directs)
    await api_post(page, "/api/cable", {"tag_id": "CAB1", "site_id": "SITE1", "amont_id": "TR1", "type": "U1000R2V", "section": "5G10"})
    await api_post(page, "/api/tableau_jointure", {"tableau_tag": "TGBT1", "amont_tag": "CAB1"})
    await api_post(page, "/api/cable", {"tag_id": "CAB2", "site_id": "SITE1", "amont_id": "TGBT1", "type": "5G2.5"})
    await api_post(page, "/api/charge", {"tag_id": "CHG1", "site_id": "SITE1", "amont_id": "CAB2", "type": "Moteur"})

    await page.goto(f"{BASE_URL}/")
    await page.wait_for_timeout(500)
    await page.click("button.top-tab-btn:has-text('Liste des equipements')")
    await page.wait_for_timeout(600)

    tree_text = await page.inner_text("#tree-root")
    chk.that("CAB2" not in tree_text, "les cables ne doivent jamais apparaitre dans l'arbre")
    chk.that("CHG1" not in tree_text, "les charges ne doivent jamais apparaitre dans l'arbre")
    chk.that("TGBT1" in tree_text, "les tableaux doivent apparaitre dans l'arbre")

    equip_text = await page.inner_text("#equip-table-wrap")
    chk.that("CAB2" not in equip_text, "les cables ne doivent jamais apparaitre dans la liste des equipements")

    # Avals directs de TR1 : doit sauter le cable intermediaire et montrer TGBT1
    tr1_row = page.locator(".tree-row:has-text('TR1')").first
    if await tr1_row.count():
        await tr1_row.click()
        await page.wait_for_timeout(400)
        avals_text = await page.inner_text("#equip-table-wrap")
        chk.that("TGBT1" in avals_text, "les avals directs de TR1 doivent afficher TGBT1 (cable traverse)")
        chk.that("CAB1" not in avals_text and "cable" not in avals_text.lower(),
                 "le cable intermediaire ne doit pas apparaitre comme un aval direct")
    else:
        chk.failures.append("noeud TR1 introuvable dans l'arbre pour tester les avals directs")

    # Glisser-depose : ajouter un tableau sur TGBT1, l'amont doit etre automatique
    # (on repart d'un chargement de page propre pour eviter tout effet de bord
    # d'une interaction precedente sur l'etat deplie/replie de l'arbre)
    try:
        await page.goto(f"{BASE_URL}/")
        await page.wait_for_timeout(500)
        await page.click("button.top-tab-btn:has-text('Liste des equipements')")
        await page.wait_for_timeout(600)

        tgbt_row = page.locator(".tree-row:has-text('TGBT1')").first
        palette_item = page.locator(".palette-item:has-text('Tableaux')")
        if await tgbt_row.count() and await palette_item.count():
            await tgbt_row.scroll_into_view_if_needed()
            src_box = await palette_item.bounding_box()
            dst_box = await tgbt_row.bounding_box()
            await page.mouse.move(src_box["x"] + src_box["width"] / 2, src_box["y"] + src_box["height"] / 2)
            await page.mouse.down()
            await page.wait_for_timeout(100)
            await page.mouse.move(dst_box["x"] + dst_box["width"] / 2, dst_box["y"] + dst_box["height"] / 2, steps=15)
            await page.wait_for_timeout(150)
            await page.mouse.up()
            await page.wait_for_timeout(400)
            modal_visible = await page.is_visible("#modal-create-equipment")
            chk.that(modal_visible, "le glisser-depose doit ouvrir la modale de creation")
            if modal_visible:
                context_text = await page.inner_text("#create-equipment-context")
                chk.that("TGBT1" in context_text, "le contexte doit mentionner TGBT1 comme amont")
                await page.fill("#c_tag_id", "TD_DND")
                await page.fill("#c_type", "TD")
                await page.click("#create-equipment-save")
                await page.wait_for_timeout(500)
                r = await api_get(page, "/api/tableau_jointure")
                created = [j for j in r["body"] if j["tableau_tag"] == "TD_DND"]
                chk.that(len(created) == 1, "le nouveau tableau doit avoir un amont automatique via tableau_jointure")
        else:
            chk.failures.append("noeud TGBT1 ou palette introuvable pour tester le glisser-depose")
    except Exception as e:
        chk.failures.append(f"glisser-depose : erreur d'interaction Playwright ({e})")

    chk.finish()


# ============================================================================
# 4. Import Caneco
# ============================================================================

async def test_caneco_import(page, caneco_pdf):
    chk = Check("4. Import Caneco")

    if not caneco_pdf or not os.path.exists(caneco_pdf):
        record("4. Import Caneco", None, "ignore (aucun fichier PDF Caneco fourni via --caneco-pdf)")
        return

    await page.goto(f"{BASE_URL}/")
    await page.wait_for_timeout(500)

    await page.click("#btn-import-toggle")
    await page.wait_for_timeout(200)
    await page.click("button.dropdown-item[data-import='caneco']")
    await page.wait_for_timeout(400)

    reseaux = await api_get(page, "/api/reseau_ht")
    chk.that(len(reseaux["body"]) >= 1, "au moins un reseau HT doit exister avant l'import (precondition)")

    await page.select_option("#caneco-reseau-select", reseaux["body"][0]["tag_id"])
    await page.set_input_files("#caneco-file", caneco_pdf)
    await page.click("#caneco-confirm")

    try:
        await page.wait_for_selector("#modal-caneco-preview", state="visible", timeout=120000)
    except Exception:
        chk.failures.append("l'analyse Caneco n'a pas produit d'apercu dans le delai imparti")
        chk.finish()
        return

    nb_rows = await page.locator("#caneco-preview-table-wrap tbody tr").count()
    chk.that(nb_rows > 0, "l'apercu doit lister au moins un tableau/transfo/groupe")

    await page.click("#caneco-preview-confirm")
    try:
        await page.wait_for_selector("#caneco-final-report", state="visible", timeout=120000)
    except Exception:
        chk.failures.append("la confirmation de l'import n'a pas produit de rapport final")
        chk.finish()
        return

    report_text = await page.inner_text("#caneco-final-report")
    chk.that("Import termine" in report_text, "le rapport final doit confirmer la fin de l'import")
    chk.that("charges" not in report_text.lower(), "les charges ne doivent pas etre importees par defaut (case decochee)")

    chk.finish()


# ============================================================================
# 5. Synoptique
# ============================================================================

async def test_synoptique(page):
    chk = Check("5. Synoptique")

    await page.goto(f"{BASE_URL}/")
    await page.wait_for_timeout(500)
    await page.click("button.top-tab-btn:has-text('Synoptique')")
    await page.wait_for_timeout(700)

    zoom_in = page.locator("#diagram-zoom-in")
    zoom_out = page.locator("#diagram-zoom-out")
    zoom_reset = page.locator("#diagram-zoom-reset")
    chk.that(await zoom_in.count() == 1, "bouton zoom+ present")
    chk.that(await zoom_out.count() == 1, "bouton zoom- present")
    chk.that(await zoom_reset.count() == 1, "bouton reinitialiser le zoom present")

    canvas = page.locator("#diagram-svg-canvas")
    if await canvas.count():
        before = await canvas.evaluate("el => getComputedStyle(el).transform")
        await zoom_in.click()
        await zoom_in.click()
        after = await canvas.evaluate("el => getComputedStyle(el).transform")
        chk.that(before != after, "le zoom doit modifier l'echelle affichee")
        await zoom_reset.click()

    # Filtre en arborescence avec decochage en cascade
    checkboxes = page.locator("#tableaux-filter-list input[type=checkbox]")
    nb_checkboxes = await checkboxes.count()
    chk.that(nb_checkboxes > 0, "le panneau de filtre doit lister au moins un equipement")

    tr1_checkbox = page.locator("span.filter-tree-label:has-text('TR1')").locator("xpath=preceding-sibling::input")
    if await tr1_checkbox.count():
        await tr1_checkbox.uncheck()
        await page.wait_for_timeout(400)
        tgbt_checkbox = page.locator("span.filter-tree-label:has-text('TGBT1')").locator("xpath=preceding-sibling::input")
        if await tgbt_checkbox.count():
            still_checked = await tgbt_checkbox.is_checked()
            chk.that(not still_checked, "decocher TR1 doit decocher ses avals (TGBT1) en cascade")
        svg = await page.inner_html("#diagram-svg-wrap")
        chk.that(">TGBT1<" not in svg, "TGBT1 (aval de TR1) ne doit plus apparaitre dans le dessin")

    chk.finish()


# ============================================================================
# 6. Carnet de cables
# ============================================================================

async def test_cable_schedule(page, workdir):
    chk = Check("6. Carnet de cables")

    await page.goto(f"{BASE_URL}/")
    await page.wait_for_timeout(500)

    tab_labels = await page.locator(".top-tab-btn").all_inner_texts()
    chk.that(len(tab_labels) >= 3 and tab_labels[1] == "Bilan de puissance" and tab_labels[2] == "Carnet de cables",
             f"le bouton doit etre positionne entre Bilan de puissance et Synoptique (ordre observe: {tab_labels})")

    await page.click("button.top-tab-btn:has-text('Carnet de cables')")
    await page.wait_for_timeout(600)

    filters = page.locator(".cable-filter-input")
    nb_filters = await filters.count()
    chk.that(nb_filters >= 8, f"un filtre par colonne doit etre present (trouve {nb_filters})")

    headers = await page.locator("#cable-schedule-table-wrap thead tr").first.inner_text()
    chk.that("Type de cable" in headers and "Section" in headers,
             "les colonnes Type de cable et Section doivent etre distinctes")

    # Export vers Excel
    export_folder = os.path.join(workdir, "export_cables")
    await page.click("#cable-schedule-export-open")
    await page.wait_for_timeout(300)
    await page.fill("#cable-export-filename", "Test_Export.xlsx")
    await page.fill("#cable-export-folder", export_folder)
    await page.click("#cable-export-confirm")
    try:
        await page.wait_for_function(
            "document.getElementById('cable-export-success').textContent.trim().length > 0 || "
            "document.getElementById('cable-export-error').textContent.trim().length > 0",
            timeout=10000,
        )
    except Exception:
        pass
    success_text = await page.inner_text("#cable-export-success")
    chk.that("Test_Export.xlsx" in success_text, "l'export Excel doit confirmer la creation du fichier")
    chk.that(os.path.exists(os.path.join(export_folder, "Test_Export.xlsx")),
             "le fichier Excel doit exister a l'emplacement choisi")

    chk.finish()


# ============================================================================
# 7. Export de la base de donnees
# ============================================================================

async def test_db_export(page, workdir):
    chk = Check("7. Export base de donnees (SQL)")

    export_folder = os.path.join(workdir, "export_db")
    await page.goto(f"{BASE_URL}/")
    await page.wait_for_timeout(500)

    tab_order = await page.evaluate(
        """() => Array.from(document.querySelector('.file-menu').children)
              .map(c => c.textContent.trim().split('\\n')[0])"""
    )
    chk.that("Exporter ▾" in tab_order and tab_order.index("Exporter ▾") == tab_order.index("Importer ▾") + 1,
             f"le bouton Exporter doit etre a droite d'Importer (ordre observe: {tab_order})")

    await page.click("#btn-export-toggle")
    await page.wait_for_timeout(200)
    await page.click("button.dropdown-item[data-export='sql']")
    await page.wait_for_timeout(300)
    await page.fill("#export-db-folder", export_folder)
    await page.click("#export-db-confirm")
    try:
        await page.wait_for_function(
            "document.getElementById('export-db-success').textContent.trim().length > 0 || "
            "document.getElementById('export-db-error').textContent.trim().length > 0",
            timeout=10000,
        )
    except Exception:
        pass
    success_text = await page.inner_text("#export-db-success")
    chk.that("Fichier cree" in success_text, "l'export SQL doit confirmer la creation du fichier")
    sql_path = os.path.join(export_folder, "NormaGrid_Export.sql")
    chk.that(os.path.exists(sql_path), "le fichier .sql doit exister")
    if os.path.exists(sql_path):
        content = open(sql_path, encoding="utf-8").read()
        chk.that("FOREIGN KEY" in content, "le script SQL doit contenir les relations (cles etrangeres)")
        chk.that("CREATE TABLE" in content, "le script SQL doit contenir la creation des tables")

    chk.finish()


# ============================================================================
# Orchestration - mode pas a pas interactif
# ============================================================================

TEST_STEPS = [
    ("1. Gestion de projet", test_project_management, lambda page, workdir, pdf: (page, workdir)),
    ("2. Saisie des donnees (CRUD)", test_crud, lambda page, workdir, pdf: (page,)),
    ("3. Arborescence des equipements", test_tree_and_dragdrop, lambda page, workdir, pdf: (page,)),
    ("4. Import Caneco", test_caneco_import, lambda page, workdir, pdf: (page, pdf)),
    ("5. Synoptique", test_synoptique, lambda page, workdir, pdf: (page,)),
    ("6. Carnet de cables", test_cable_schedule, lambda page, workdir, pdf: (page, workdir)),
    ("7. Export base de donnees (SQL)", test_db_export, lambda page, workdir, pdf: (page, workdir)),
]


async def ask(loop, message):
    """Question posee dans la console, sans bloquer la boucle asyncio."""
    return await loop.run_in_executor(None, input, message)


def append_comment(comments_path, test_name, status, message, user_comment):
    from datetime import datetime
    with open(comments_path, "a", encoding="utf-8") as f:
        f.write(f"=== {test_name} ===\n")
        f.write(f"Date : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Resultat automatique : {status}\n")
        if message:
            f.write(f"Detail automatique : {message}\n")
        f.write(f"Commentaire utilisateur : {user_comment or '(aucun)'}\n")
        f.write("-" * 60 + "\n\n")


async def run_all_tests(caneco_pdf):
    from playwright.async_api import async_playwright
    import tempfile

    loop = asyncio.get_event_loop()

    # Seule information demandee a l'utilisateur pour toute la session : le
    # fichier PDF Caneco (une seule fois, au debut). Toutes les autres
    # donnees (client, projet, site, reseau HT...) sont des donnees de test
    # fixes, jamais demandees.
    if not caneco_pdf:
        reponse = (await ask(
            loop,
            "Chemin du fichier PDF Caneco a tester "
            "(glissez-deposez le fichier ici, ou Entree pour ignorer ce test) : "
        )).strip().strip('"')
        if reponse:
            caneco_pdf = reponse

    workdir = os.path.join(tempfile.gettempdir(), "normagrid_test_workspace")
    shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir, exist_ok=True)

    comments_path = os.path.join(HERE, "commentaires_tests.txt")
    print(f"Les commentaires de cette session seront ajoutes a : {comments_path}")
    print("(a transmettre ensuite pour d'eventuelles corrections)\n")

    env = os.environ.copy()
    env["FLASK_RUN_PORT"] = str(PORT)
    server_log_path = os.path.join(workdir, "server.log")
    server_log = open(server_log_path, "w")
    server = subprocess.Popen(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {HERE!r}); "
         f"import app as a; a.app.run(host='127.0.0.1', port={PORT}, debug=False, use_reloader=False)"],
        cwd=HERE, stdout=server_log, stderr=subprocess.STDOUT, env=env,
    )

    try:
        if not wait_for_server(BASE_URL):
            server_log.flush()
            print("ERREUR : le serveur NormaGrid n'a pas demarre.")
            print(f"Contenu de {server_log_path} :")
            print("-" * 60)
            try:
                with open(server_log_path, encoding="utf-8", errors="replace") as f:
                    print(f.read())
            except OSError as e:
                print(f"(impossible de lire le journal : {e})")
            print("-" * 60)
            sys.exit(1)

        async with async_playwright() as p:
            # headless=False : la fenetre du navigateur reste visible a
            # l'ecran pendant toute la session, pour pouvoir suivre chaque
            # test au fur et a mesure.
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page(viewport={"width": 1400, "height": 950})
            await page.goto(f"{BASE_URL}/")
            await page.wait_for_timeout(300)

            for step_name, test_fn, args_builder in TEST_STEPS:
                print("\n" + "=" * 60)
                print(f"  ETAPE : {step_name}")
                print("=" * 60)

                before = len(RESULTS)
                try:
                    await test_fn(*args_builder(page, workdir, caneco_pdf))
                except Exception as e:
                    record(test_fn.__name__, False, f"exception non geree pendant le test : {e}")

                # Le resultat de CE test est la (ou les) entree(s) ajoutee(s)
                # a RESULTS depuis le debut de cette etape.
                new_entries = RESULTS[before:]
                for name, ok, msg in new_entries:
                    status = "PASS" if ok is True else ("SKIP" if ok is None else "FAIL")
                    print(f"\n>>> Resultat automatique : [{status}] {name}" + (f" -- {msg}" if msg else ""))

                user_comment = await ask(
                    loop,
                    "\nValidez-vous ce resultat ? Appuyez sur Entree pour passer a l'etape "
                    "suivante, ou tapez un commentaire a consigner (ce qui ne correspond pas a "
                    "ce que vous attendiez, une anomalie visuelle, etc.) : "
                )
                for name, ok, msg in new_entries:
                    status = "PASS" if ok is True else ("SKIP" if ok is None else "FAIL")
                    append_comment(comments_path, name, status, msg, user_comment)

            await browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except Exception:
            server.kill()
        server_log.close()

    print("\n" + "=" * 60)
    print("RAPPORT FINAL")
    print("=" * 60)
    passed = sum(1 for _, ok, _ in RESULTS if ok is True)
    failed = sum(1 for _, ok, _ in RESULTS if ok is False)
    skipped = sum(1 for _, ok, _ in RESULTS if ok is None)
    for name, ok, msg in RESULTS:
        status = "PASS" if ok is True else ("SKIP" if ok is None else "FAIL")
        print(f"  [{status}] {name}" + (f" -- {msg}" if msg else ""))
    print("-" * 60)
    print(f"Total : {len(RESULTS)}   Reussis : {passed}   Echoues : {failed}   Ignores : {skipped}")
    print(f"Commentaires enregistres dans : {comments_path}")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--caneco-pdf", default=None, help="Chemin vers un fichier PDF Caneco pour tester l'import (optionnel)")
    args = parser.parse_args()

    ok = asyncio.run(run_all_tests(args.caneco_pdf))
    sys.exit(0 if ok else 1)
