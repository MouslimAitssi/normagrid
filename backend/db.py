import sqlite3
import os
import re
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
STATE_PATH = os.path.join(BASE_DIR, "database", "current_project.json")
REGISTRY_PATH = os.path.join(BASE_DIR, "database", "projects_registry.json")
SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")

os.makedirs(PROJECTS_DIR, exist_ok=True)


class NoActiveProject(Exception):
    """Aucun projet n'est ouvert pour le moment."""


def _safe_name(name):
    name = name.strip()
    name = re.sub(r"[^A-Za-z0-9 _-]", "", name)
    name = re.sub(r"\s+", "_", name)
    if not name:
        raise ValueError("Nom de projet invalide")
    return name


def _read_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def get_active_project():
    """Chemin absolu du fichier .db actuellement ouvert, ou None."""
    return _read_json(STATE_PATH, {"active": None}).get("active")


def set_active_project(path):
    _write_json(STATE_PATH, {"active": path})
    if path:
        _register(path)


# ---------------------------------------------------------------------------
# Registre des projets connus (independant de leur emplacement sur le disque)
# ---------------------------------------------------------------------------

def _load_registry():
    return _read_json(REGISTRY_PATH, {"paths": []})["paths"]


def _save_registry(paths):
    _write_json(REGISTRY_PATH, {"paths": paths})


def _register(path):
    paths = _load_registry()
    if path not in paths:
        paths.append(path)
        _save_registry(paths)


def _unregister(path):
    paths = [p for p in _load_registry() if p != path]
    _save_registry(paths)


def list_projects():
    active = get_active_project()
    paths = _load_registry()
    result = []
    cleaned = []
    for path in paths:
        if not os.path.exists(path):
            continue  # fichier deplace/supprime depuis : on nettoie le registre
        cleaned.append(path)
        stat = os.stat(path)
        result.append({
            "path": path,
            "name": os.path.splitext(os.path.basename(path))[0],
            "folder": os.path.dirname(path),
            "size_kb": round(stat.st_size / 1024, 1),
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "active": path == active,
        })
    if cleaned != paths:
        _save_registry(cleaned)
    return sorted(result, key=lambda p: p["modified"], reverse=True)


# ---------------------------------------------------------------------------
# Creation / ouverture / fermeture / enregistrer-sous / import
# ---------------------------------------------------------------------------

def create_project(name, folder=None):
    folder = folder.strip() if folder else PROJECTS_DIR
    os.makedirs(folder, exist_ok=True)
    filename = _safe_name(name) + ".db"
    path = os.path.join(folder, filename)
    if os.path.exists(path):
        raise ValueError(f"Un projet nomme \"{name}\" existe deja a cet emplacement")
    conn = sqlite3.connect(path)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    set_active_project(path)
    return path


def open_project(path):
    path = path.strip()
    if not os.path.exists(path):
        raise ValueError("Ce fichier projet est introuvable a cet emplacement")
    set_active_project(path)
    return path


def close_project():
    set_active_project(None)


def save_project_as(name, folder=None):
    """Duplique le projet actuellement ouvert vers un nouveau fichier, qui devient actif."""
    active = get_active_project()
    if not active:
        raise NoActiveProject("Aucun projet n'est ouvert")
    folder = folder.strip() if folder else PROJECTS_DIR
    os.makedirs(folder, exist_ok=True)
    filename = _safe_name(name) + ".db"
    dest_path = os.path.join(folder, filename)
    if os.path.exists(dest_path):
        raise ValueError(f"Un projet nomme \"{name}\" existe deja a cet emplacement")
    with open(active, "rb") as src, open(dest_path, "wb") as dst:
        dst.write(src.read())
    set_active_project(dest_path)
    return dest_path


def import_project_file(source_path, name, folder=None):
    """Copie un fichier .db externe (ancienne version de NormaGrid) comme nouveau projet."""
    try:
        test_conn = sqlite3.connect(source_path)
        tables = [r[0] for r in test_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        test_conn.close()
    except sqlite3.DatabaseError:
        raise ValueError("Le fichier fourni n'est pas une base de donnees NormaGrid valide")
    if "tag" not in tables:
        raise ValueError("Le fichier fourni ne correspond pas a un projet NormaGrid (table 'tag' absente)")

    folder = folder.strip() if folder else PROJECTS_DIR
    os.makedirs(folder, exist_ok=True)
    filename = _safe_name(name) + ".db"
    dest_path = os.path.join(folder, filename)
    if os.path.exists(dest_path):
        raise ValueError(f"Un projet nomme \"{name}\" existe deja a cet emplacement")

    with open(source_path, "rb") as src, open(dest_path, "wb") as dst:
        dst.write(src.read())
    set_active_project(dest_path)
    return dest_path


def get_connection():
    active = get_active_project()
    if not active:
        raise NoActiveProject("Aucun projet n'est ouvert")
    conn = sqlite3.connect(active)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _migrate_schema(conn)
    return conn


# Colonnes ajoutees apres la creation initiale du schema : on les ajoute a la
# volee sur les anciens fichiers-projets qui ne les ont pas encore, pour ne
# jamais casser un projet existant.
_SCHEMA_MIGRATIONS = {
    "tableaux": [("amont_id", "TEXT")],
    "transfos": [("protection_modele", "TEXT"), ("calibre_a", "REAL"), ("differentiel_ma", "REAL")],
    "cable": [("protection_modele", "TEXT"), ("calibre_a", "REAL"), ("differentiel_ma", "REAL"), ("longueur_m", "REAL"), ("section", "TEXT")],
    "charge": [
        ("protection_modele", "TEXT"), ("calibre_a", "REAL"), ("differentiel_ma", "REAL"),
        ("rev", "TEXT"), ("system_area", "TEXT"), ("equipment_name", "TEXT"),
        ("installed_power_kw", "REAL"), ("absorbed_power", "REAL"), ("voltage", "REAL"),
        ("phase", "TEXT"), ("freq", "REAL"), ("special_reqts", "TEXT"),
        ("w_s", "TEXT"), ("c_i", "TEXT"), ("e_ne", "TEXT"), ("pct_e", "REAL"),
        ("unite", "TEXT"), ("type_equipement", "TEXT"), ("vitesse", "REAL"),
        ("contenu", "TEXT"), ("nombre", "REAL"), ("p_vfd", "REAL"),
        ("cos_phi_vfd", "REAL"), ("rend_vfd", "REAL"), ("longueur", "REAL"),
        ("mode_de_pose", "TEXT"),
        ("k_util", "REAL"), ("k_simul", "REAL"), ("cos_phi", "REAL"), ("rendement", "REAL"),
        ("switchgear_mcc", "TEXT"), ("equipment_tag_no", "TEXT"), ("puissance", "REAL"),
    ],
    "tableau_jointure": [("protection_modele", "TEXT"), ("calibre_a", "REAL"), ("differentiel_ma", "REAL")],
    "import_caneco_staging": [
        ("board_designation", "TEXT"), ("nombre", "TEXT"), ("consommation", "TEXT"),
        ("i_delta_n", "TEXT"), ("ir", "TEXT"), ("im_isd", "TEXT"), ("affectation_phases", "TEXT"),
    ],
}


_NEW_TABLES_SQL = {
    "reference_charge_types": """
        CREATE TABLE IF NOT EXISTS reference_charge_types (
            value TEXT PRIMARY KEY
        );
    """,
    "reference_puissances_transfos_kva": """
        CREATE TABLE IF NOT EXISTS reference_puissances_transfos_kva (
            value REAL PRIMARY KEY,
            label TEXT NOT NULL
        );
    """,
    "reference_puissances_groupes_electrogenes_kva": """
        CREATE TABLE IF NOT EXISTS reference_puissances_groupes_electrogenes_kva (
            value REAL PRIMARY KEY,
            label TEXT NOT NULL
        );
    """,
    "import_caneco_staging": """
        CREATE TABLE IF NOT EXISTS import_caneco_staging (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            board_repere        TEXT,
            board_designation   TEXT,
            amont_normal        TEXT,
            amont_secours       TEXT,
            circuit_repere      TEXT,
            circuit_designation TEXT,
            nombre              TEXT,
            consommation        TEXT,
            alimentation        TEXT,
            jdb_amont           TEXT,
            liaison_type        TEXT,
            longueur            TEXT,
            ame                 TEXT,
            l_max_prot          TEXT,
            delta_u_circuit     TEXT,
            delta_u_totale      TEXT,
            cable               TEXT,
            neutre              TEXT,
            pe_pen              TEXT,
            separe              TEXT,
            taux_harmonique     TEXT,
            protection          TEXT,
            calibre             TEXT,
            i_delta_n           TEXT,
            ir                  TEXT,
            im_isd              TEXT,
            affectation_phases  TEXT,
            type_detecte        TEXT,
            converti            INTEGER DEFAULT 0
        );
    """,
}


def _migrate_schema(conn):
    existing_tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    for table, ddl in _NEW_TABLES_SQL.items():
        if table not in existing_tables:
            conn.executescript(ddl)
            existing_tables.add(table)

    for table, columns in _SCHEMA_MIGRATIONS.items():
        if table not in existing_tables:
            continue  # table absente (tres ancien projet incomplet) : rien a migrer ici
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col_name, col_type in columns:
            if col_name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")

    # Donnees de reference livrees avec l'application. INSERT OR IGNORE les
    # preserve si l'utilisateur enrichit ces listes dans un projet.
    conn.executemany(
        "INSERT OR IGNORE INTO reference_charge_types (value) VALUES (?)",
        [("U1000R2V 4G10",), ("U1000R2V 4G16",), ("U1000R2V 4G25",),
         ("U1000R2V 4G35",), ("U1000R2V 4G50",)],
    )
    power_tables = (
        "reference_puissances_transfos_kva",
        "reference_puissances_groupes_electrogenes_kva",
    )
    if "reference_puissances_kva" in existing_tables:
        for table in power_tables:
            conn.execute(
                f"INSERT OR IGNORE INTO {table} (value, label) "
                "SELECT value, label FROM reference_puissances_kva"
            )
    for table in power_tables:
        conn.executemany(
            f"INSERT OR IGNORE INTO {table} (value, label) VALUES (?, ?)",
            [(250, "250"), (400, "400"), (630, "630"), (800, "800")],
        )
        conn.execute(
            f"UPDATE {table} SET label = CAST(value AS INTEGER) "
            "WHERE value IN (250, 400, 630, 800)"
        )
    conn.commit()


def init_db():
    """Au demarrage : s'assure qu'un projet est actif (le dernier connu, sinon un projet 'Default')."""
    active = get_active_project()
    if active and os.path.exists(active):
        return
    known = [p for p in _load_registry() if os.path.exists(p)]
    if known:
        set_active_project(sorted(known, key=lambda p: os.stat(p).st_mtime, reverse=True)[0])
    else:
        create_project("Default")
