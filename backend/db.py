import sqlite3
import os
import re
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# En production, Render monte le disque persistant dans /var/data.  Les
# fichiers SQLite et l'etat du projet doivent y vivre, sinon ils seraient
# supprimes a chaque redeploiement.  Sans cette variable, le comportement
# historique en local est conserve.
DATA_DIR = os.environ.get("NORMAGRID_DATA_DIR")
if DATA_DIR:
    PROJECTS_DIR = os.path.join(DATA_DIR, "projects")
    STATE_PATH = os.path.join(DATA_DIR, "current_project.json")
    REGISTRY_PATH = os.path.join(DATA_DIR, "projects_registry.json")
else:
    PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
    STATE_PATH = os.path.join(BASE_DIR, "database", "current_project.json")
    REGISTRY_PATH = os.path.join(BASE_DIR, "database", "projects_registry.json")
SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")

os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
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
    # SQLite reste mono-instance sur Render. Le delai evite les erreurs
    # "database is locked" lors de deux requetes tres proches.
    conn = sqlite3.connect(active, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
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
    "reference_charges": """
        CREATE TABLE IF NOT EXISTS reference_charges (
            id INTEGER PRIMARY KEY,
            designation TEXT NOT NULL,
            type_conso TEXT,
            consom TEXT,
            typ_recept REAL,
            p_electrique_w REAL,
            polarite REAL,
            rendement REAL,
            i_nominal REAL,
            is_50hz INTEGER,
            is_60hz INTEGER,
            is_dc INTEGER,
            k_utilisation REAL,
            k_foison REAL,
            cos_phi REAL,
            cos_phi_dem REAL,
            id_sur_in REAL,
            un_min REAL,
            un_max REAL
        );
    """,
    "reference_cables": """
        CREATE TABLE IF NOT EXISTS reference_cables (
            id INTEGER PRIMARY KEY,
            designation TEXT NOT NULL,
            famille_cable TEXT,
            section TEXT,
            section_txt TEXT,
            section_reelle REAL,
            nb_conducteur REAL,
            metal_ame REAL,
            is_arme INTEGER,
            type_conduct REAL,
            vert_jaune INTEGER,
            famille_cu_al TEXT,
            temp_max REAL,
            diametre REAL,
            poids REAL,
            iz_air REAL,
            un REAL,
            un_max REAL,
            raw_data_json TEXT NOT NULL
        );
    """,
    "reference_puissances_transfos_kva": """
        CREATE TABLE IF NOT EXISTS reference_puissances_transfos_kva (
            puissance_kva REAL PRIMARY KEY,
            hta_kv REAL,
            bt_v REAL,
            couplage TEXT,
            isolant TEXT,
            uk_ute_pct REAL,
            p0_ute_w REAL,
            pk_ute_w REAL,
            i0_ute_pct REAL,
            p0_tier2_max_w REAL,
            pk_tier2_max_w REAL,
            gain_p0_w REAL,
            reduction_p0_pct REAL,
            gain_pk_w REAL,
            reduction_pk_pct REAL,
            in_bt_a REAL,
            ik3_ute_approx_ka REAL
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


_TRANSFORMER_REFERENCE_COLUMNS = (
    "puissance_kva", "hta_kv", "bt_v", "couplage", "isolant", "uk_ute_pct",
    "p0_ute_w", "pk_ute_w", "i0_ute_pct", "p0_tier2_max_w", "pk_tier2_max_w",
    "gain_p0_w", "reduction_p0_pct", "gain_pk_w", "reduction_pk_pct", "in_bt_a",
    "ik3_ute_approx_ka",
)

# Catalogue des transformateurs issu de « Table TR.xlsx ».
_TRANSFORMER_REFERENCE_ROWS = [
    (100, 20, 400, "Dyn11", "Huile / ONAN", 4, 210, 2150, 2.5, 130, 1250, 80, 0.38095238095238093, 900, 0.4186046511627907, 144.33756729740645, 3.608439182435161),
    (160, 20, 400, "Dyn11", "Huile / ONAN", 4, 460, 2350, 2.3, 189, 1750, 271, 0.5891304347826087, 600, 0.2553191489361702, 230.9401076758503, 5.773502691896257),
    (250, 20, 400, "Dyn11", "Huile / ONAN", 4, 650, 3250, 2.1, 270, 2350, 380, 0.5846153846153846, 900, 0.27692307692307694, 360.8439182435161, 9.021097956087901),
    (315, 20, 400, "Dyn11", "Huile / ONAN", 4, 800, 3900, 2, 324, 2800, 476, 0.595, 1100, 0.28205128205128205, 454.6633369868303, 11.366583424670758),
    (400, 20, 400, "Dyn11", "Huile / ONAN", 4, 930, 4600, 1.9, 387, 3250, 543, 0.5838709677419355, 1350, 0.29347826086956524, 577.3502691896258, 14.433756729740644),
    (500, 20, 400, "Dyn11", "Huile / ONAN", 4, 1100, 5500, 1.9, 459, 3900, 641, 0.5827272727272728, 1600, 0.2909090909090909, 721.6878364870322, 18.042195912175803),
    (630, 20, 400, "Dyn11", "Huile / ONAN", 4, 1300, 6500, 1.8, 540, 4600, 760, 0.5846153846153846, 1900, 0.2923076923076923, 909.3266739736606, 22.733166849341515),
    (800, 20, 400, "Dyn11", "Huile / ONAN", 6, 1220, 10700, 2.5, 585, 6000, 635, 0.5204918032786885, 4700, 0.4392523364485981, 1154.7005383792516, 19.245008972987527),
    (1000, 20, 400, "Dyn11", "Huile / ONAN", 6, 1470, 13000, 2.4, 693, 7600, 777, 0.5285714285714286, 5400, 0.4153846153846154, 1443.3756729740644, 24.056261216234407),
    (1250, 20, 400, "Dyn11", "Huile / ONAN", 6, 1800, 16000, 2.2, 855, 9500, 945, 0.525, 6500, 0.40625, 1804.2195912175805, 30.07032652029301),
    (1600, 20, 400, "Dyn11", "Huile / ONAN", 6, 2300, 20000, 2, 1080, 12000, 1220, 0.5304347826086957, 8000, 0.4, 2309.401076758503, 38.490017945975055),
    (2000, 20, 400, "Dyn11", "Huile / ONAN", 6, 2750, 25500, 1.9, 1305, 15000, 1445, 0.5254545454545455, 10500, 0.4117647058823529, 2886.751345948129, 48.112522432468815),
    (2500, 20, 400, "Dyn11", "Huile / ONAN", 6, 3350, 32000, 1.8, 1575, 18500, 1775, 0.5298507462686567, 13500, 0.421875, 3608.439182435161, 60.14065304058602),
    (3150, 20, 400, "Dyn11", "Huile / ONAN", 7, 4380, 33000, 1.7, 1980, 23000, 2400, 0.547945205479452, 10000, 0.30303030303030304, 4546.633369868303, 64.9519052838329),
]


def _migrate_schema(conn):
    existing_tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    for table, ddl in _NEW_TABLES_SQL.items():
        if table not in existing_tables:
            conn.executescript(ddl)
            existing_tables.add(table)

    # Migration de l'ancienne reference simplifiee (value, label) vers le
    # catalogue technique complet. Les anciennes puissances restent preservees.
    transfo_ref_columns = {
        row[1] for row in conn.execute(
            "PRAGMA table_info(reference_puissances_transfos_kva)"
        ).fetchall()
    }
    if "value" in transfo_ref_columns and "puissance_kva" not in transfo_ref_columns:
        legacy_table = "reference_puissances_transfos_kva_legacy"
        conn.execute(f"DROP TABLE IF EXISTS {legacy_table}")
        conn.execute(
            "ALTER TABLE reference_puissances_transfos_kva "
            f"RENAME TO {legacy_table}"
        )
        conn.executescript(_NEW_TABLES_SQL["reference_puissances_transfos_kva"])
        conn.execute(
            "INSERT OR IGNORE INTO reference_puissances_transfos_kva (puissance_kva) "
            f"SELECT value FROM {legacy_table} WHERE value IS NOT NULL"
        )
        conn.execute(f"DROP TABLE {legacy_table}")

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
    if "reference_puissances_kva" in existing_tables:
        conn.execute(
            "INSERT OR IGNORE INTO reference_puissances_groupes_electrogenes_kva (value, label) "
            "SELECT value, label FROM reference_puissances_kva"
        )
    conn.executemany(
        "INSERT OR IGNORE INTO reference_puissances_groupes_electrogenes_kva (value, label) VALUES (?, ?)",
        [(250, "250"), (400, "400"), (630, "630"), (800, "800")],
    )
    conn.execute(
        "UPDATE reference_puissances_groupes_electrogenes_kva "
        "SET label = CAST(value AS INTEGER) WHERE value IN (250, 400, 630, 800)"
    )

    columns_sql = ", ".join(_TRANSFORMER_REFERENCE_COLUMNS)
    placeholders = ", ".join("?" for _ in _TRANSFORMER_REFERENCE_COLUMNS)
    updates_sql = ", ".join(
        f"{column}=excluded.{column}" for column in _TRANSFORMER_REFERENCE_COLUMNS[1:]
    )
    conn.executemany(
        f"INSERT INTO reference_puissances_transfos_kva ({columns_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT(puissance_kva) DO UPDATE SET {updates_sql}",
        _TRANSFORMER_REFERENCE_ROWS,
    )
    conn.commit()


def init_db():
    """Au demarrage : s'assure qu'un projet est actif (le dernier connu, sinon un projet 'Default')."""
    active = get_active_project()
    if active and os.path.exists(active):
        pass
    else:
        known = [p for p in _load_registry() if os.path.exists(p)]
        if known:
            set_active_project(sorted(known, key=lambda p: os.stat(p).st_mtime, reverse=True)[0])
        else:
            create_project("Default")

    # Applique les migrations (colonnes et catalogues de reference) avant la
    # premiere requete HTTP, y compris pour un projet deja existant.
    conn = get_connection()
    conn.close()
