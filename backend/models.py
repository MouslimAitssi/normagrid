"""
Config centrale du schema (source unique) + fonctions CRUD generiques.
Le frontend recupere cette config via GET /api/schema pour construire
les formulaires dynamiquement : une seule source de verite.
"""

from backend.db import get_connection
from backend import caneco_import
import re
import math

# ---------------------------------------------------------------------------
# Description des tables : colonnes, cles primaires, cles etrangeres.
# "auto_tag_type" : si present, une ligne est automatiquement creee/mise a
# jour dans la table `tag` (tag=valeur de la PK, type=auto_tag_type) a chaque
# insertion -- ca evite a l'utilisateur de devoir remplir `tag` a la main.
# ---------------------------------------------------------------------------
TABLES = {
    "client": {
        "label": "Client",
        "pk": ["tag"],
        "columns": [
            {"name": "tag", "label": "Tag", "type": "text", "pk": True},
            {"name": "nom", "label": "Nom", "type": "text"},
        ],
        "fk": {},
    },
    "projet": {
        "label": "Projet",
        "pk": ["tag"],
        "columns": [
            {"name": "tag", "label": "Tag", "type": "text", "pk": True},
            {"name": "client_tag", "label": "Client", "type": "text", "fk": "client"},
            {"name": "nom", "label": "Nom", "type": "text"},
        ],
        "fk": {"client_tag": "client"},
    },
    "site": {
        "label": "Site",
        "pk": ["tag"],
        "columns": [
            {"name": "tag", "label": "Tag", "type": "text", "pk": True},
            {"name": "client_tag", "label": "Projet", "type": "text", "fk": "projet"},
            {"name": "nom", "label": "Nom", "type": "text"},
        ],
        "fk": {"client_tag": "projet"},
    },
    "tag": {
        "label": "Tag (registre central)",
        "pk": ["tag"],
        "columns": [
            {"name": "tag", "label": "Tag", "type": "text", "pk": True},
            {"name": "type", "label": "Type", "type": "text"},
        ],
        "fk": {},
    },
    # Tables de reference : elles alimentent les listes deroulantes mais ne
    # sont pas exposees comme onglets de saisie dans l'interface principale.
    "reference_charge_types": {
        "label": "Types de charges (reference)",
        "pk": ["value"],
        "columns": [
            {"name": "value", "label": "Type", "type": "text", "pk": True},
        ],
        "fk": {},
    },
    "reference_puissances_transfos_kva": {
        "label": "Puissances transformateurs (reference)",
        "pk": ["value"],
        "columns": [
            {"name": "value", "label": "Valeur (kVA)", "type": "number", "pk": True},
            {"name": "label", "label": "Libelle", "type": "text"},
        ],
        "fk": {},
    },
    "reference_puissances_groupes_electrogenes_kva": {
        "label": "Puissances groupes electrogenes (reference)",
        "pk": ["value"],
        "columns": [
            {"name": "value", "label": "Valeur (kVA)", "type": "number", "pk": True},
            {"name": "label", "label": "Libelle", "type": "text"},
        ],
        "fk": {},
    },
    "tableaux": {
        "label": "Tableaux",
        "pk": ["tag_id"],
        "auto_tag_type": "tableaux",
        "columns": [
            {"name": "tag_id", "label": "Tag", "type": "text", "pk": True},
            {"name": "site_id", "label": "Site", "type": "text", "fk": "site"},
            {"name": "type", "label": "Type", "type": "text"},
            {"name": "tension_v", "label": "Tension (V)", "type": "number"},
            {"name": "amont_id", "label": "Amont", "type": "text", "fk": "tag", "optional": True},
        ],
        "fk": {"site_id": "site", "amont_id": "tag"},
    },
    "transfos": {
        "label": "Transformateurs",
        "pk": ["tag_id"],
        "auto_tag_type": "transfos",
        "columns": [
            {"name": "tag_id", "label": "Tag", "type": "text", "pk": True},
            {"name": "site_id", "label": "Site", "type": "text", "fk": "site"},
            {"name": "puissance_kva", "label": "Puissance (kVA)", "type": "number", "options_table": "reference_puissances_transfos_kva"},
            {"name": "amont_id", "label": "Amont", "type": "text", "fk": "tag"},
            {"name": "protection_modele", "label": "Protection (modele)", "type": "text", "optional": True},
            {"name": "calibre_a", "label": "Calibre (A)", "type": "number", "optional": True},
            {"name": "differentiel_ma", "label": "Differentiel (mA)", "type": "number", "optional": True},
        ],
        "fk": {"site_id": "site", "amont_id": "tag"},
    },
    "groupes_electrogenes": {
        "label": "Groupes electrogenes",
        "pk": ["tag_id"],
        "auto_tag_type": "groupes_electrogenes",
        "columns": [
            {"name": "tag_id", "label": "Tag", "type": "text", "pk": True},
            {"name": "site_id", "label": "Site", "type": "text", "fk": "site"},
            {"name": "puissance_kva", "label": "Puissance (kVA)", "type": "number", "options_table": "reference_puissances_groupes_electrogenes_kva"},
        ],
        "fk": {"site_id": "site"},
    },
    "reseau_ht": {
        "label": "Reseau HT",
        "pk": ["tag_id"],
        "auto_tag_type": "reseau_ht",
        "columns": [
            {"name": "tag_id", "label": "Tag", "type": "text", "pk": True},
            {"name": "site_id", "label": "Site", "type": "text", "fk": "site"},
            {"name": "nom", "label": "Nom", "type": "text"},
            {"name": "tension_kv", "label": "Tension (kV)", "type": "number"},
            {"name": "pcc_max_mva", "label": "Pcc max (MVA)", "type": "number"},
            {"name": "x_r_max", "label": "X/R max", "type": "number"},
            {"name": "pcc_min_mva", "label": "Pcc min (MVA)", "type": "number"},
            {"name": "x_r_min", "label": "X/R min", "type": "number"},
        ],
        "fk": {"site_id": "site"},
    },
    "cable": {
        "label": "Cables",
        "pk": ["tag_id"],
        "auto_tag_type": "cable",
        "columns": [
            {"name": "tag_id", "label": "Tag", "type": "text", "pk": True},
            {"name": "site_id", "label": "Site", "type": "text", "fk": "site"},
            {"name": "amont_id", "label": "Amont", "type": "text", "fk": "tag"},
            {"name": "type", "label": "Type", "type": "text", "options_table": "reference_charge_types"},
            {"name": "section", "label": "Section", "type": "text", "optional": True},
            {"name": "longueur_m", "label": "Longueur (m)", "type": "number", "optional": True},
            {"name": "protection_modele", "label": "Protection (modele)", "type": "text", "optional": True},
            {"name": "calibre_a", "label": "Calibre (A)", "type": "number", "optional": True},
            {"name": "differentiel_ma", "label": "Differentiel (mA)", "type": "number", "optional": True},
        ],
        "fk": {"site_id": "site", "amont_id": "tag"},
    },
    "charge": {
        "label": "Charges",
        "pk": ["tag_id"],
        "auto_tag_type": "charge",
        "columns": [
            {"name": "tag_id", "label": "Tag", "type": "text", "pk": True},
            {"name": "site_id", "label": "Site", "type": "text", "fk": "site"},
            {"name": "type", "label": "Type", "type": "text"},
            {"name": "unite", "label": "Unite", "type": "text"},
            {"name": "cos_phi", "label": "Cos \u03c6", "type": "number"},
            {"name": "amont_id", "label": "Amont", "type": "text", "fk": "tag"},
            {"name": "puissance", "label": "Puissance", "type": "number", "optional": True},
            {"name": "installed_power_kw", "label": "Installed power (kW)", "type": "number"},
            {"name": "protection_modele", "label": "Protection (modele)", "type": "text", "optional": True},
            {"name": "calibre_a", "label": "Calibre (A)", "type": "number", "optional": True},
            {"name": "differentiel_ma", "label": "Differentiel (mA)", "type": "number", "optional": True},
            {"name": "rev", "label": "Rev", "type": "text", "optional": True},
            {"name": "system_area", "label": "System / Area", "type": "text", "optional": True},
            {"name": "equipment_name", "label": "Equipment Name", "type": "text", "optional": True},
            {"name": "absorbed_power", "label": "Absorbed power", "type": "number", "optional": True},
            {"name": "voltage", "label": "Voltage", "type": "number", "optional": True},
            {"name": "phase", "label": "Phase", "type": "text", "optional": True},
            {"name": "freq", "label": "Freq", "type": "number", "optional": True},
            {"name": "special_reqts", "label": "Special Reqts", "type": "text", "optional": True},
            {"name": "w_s", "label": "W/S", "type": "text", "optional": True},
            {"name": "c_i", "label": "C/I", "type": "text", "optional": True},
            {"name": "e_ne", "label": "E/NE", "type": "text", "optional": True},
            {"name": "pct_e", "label": "% E", "type": "number", "optional": True},
            {"name": "type_equipement", "label": "Type", "type": "text", "optional": True},
            {"name": "vitesse", "label": "Vitesse", "type": "number", "optional": True},
            {"name": "contenu", "label": "Contenu", "type": "text", "optional": True},
            {"name": "nombre", "label": "Nombre", "type": "number", "optional": True},
            {"name": "p_vfd", "label": "P VFD", "type": "number", "optional": True},
            {"name": "cos_phi_vfd", "label": "Cos \u03c6 VFD (%)", "type": "number", "optional": True},
            {"name": "rend_vfd", "label": "Rend VFD (%)", "type": "number", "optional": True},
            {"name": "longueur", "label": "Longueur", "type": "number", "optional": True},
            {"name": "mode_de_pose", "label": "Mode de pose", "type": "text", "optional": True},
            {"name": "k_util", "label": "K.Util", "type": "number", "optional": True},
            {"name": "k_simul", "label": "K.Simul", "type": "number", "optional": True},
            {"name": "rendement", "label": "Rendement", "type": "number", "optional": True},
            {"name": "switchgear_mcc", "label": "Switchgear / MCC", "type": "text", "optional": True},
            {"name": "equipment_tag_no", "label": "Equipment Tag No", "type": "text", "optional": True},
        ],
        "fk": {"site_id": "site", "amont_id": "tag"},
    },
    "tableau_jointure": {
        "label": "Amonts multiples (tableau <-> amont)",
        "pk": ["tableau_tag", "amont_tag"],
        "columns": [
            {"name": "tableau_tag", "label": "Tableau", "type": "text", "pk": True, "fk": "tableaux"},
            {"name": "amont_tag", "label": "Amont", "type": "text", "pk": True, "fk": "tag"},
            {"name": "protection_modele", "label": "Protection (modele)", "type": "text", "optional": True},
            {"name": "calibre_a", "label": "Calibre (A)", "type": "number", "optional": True},
            {"name": "differentiel_ma", "label": "Differentiel (mA)", "type": "number", "optional": True},
        ],
        "fk": {"tableau_tag": "tableaux", "amont_tag": "tag"},
    },
}


def get_schema():
    return TABLES


def list_rows(table):
    cfg = TABLES[table]
    cols = ", ".join(c["name"] for c in cfg["columns"])
    conn = get_connection()
    rows = conn.execute(f"SELECT {cols} FROM {table}").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_row(table, data):
    cfg = TABLES[table]
    col_names = [c["name"] for c in cfg["columns"]]
    values = {c: data.get(c) or None for c in col_names}

    conn = get_connection()
    try:
        # Auto-upsert dans `tag` pour les tables d'equipement (evite la saisie
        # manuelle du registre central).
        auto_type = cfg.get("auto_tag_type")
        if auto_type:
            pk_col = cfg["pk"][0]
            conn.execute(
                "INSERT INTO tag (tag, type) VALUES (?, ?) "
                "ON CONFLICT(tag) DO UPDATE SET type=excluded.type",
                (values[pk_col], auto_type),
            )

        placeholders = ", ".join("?" for _ in col_names)
        conn.execute(
            f"INSERT INTO {table} ({', '.join(col_names)}) VALUES ({placeholders})",
            [values[c] for c in col_names],
        )
        conn.commit()
    finally:
        conn.close()


TYPE_LABELS = {
    "tableaux": "Tableau", "transfos": "Transformateur", "groupes_electrogenes": "Groupe electrogene",
    "reseau_ht": "Reseau HT", "charge": "Charge", "cable": "Cable",
}


def get_cable_schedule():
    """
    Carnet de cables (tenant/aboutissant) du projet actuellement ouvert :
    une ligne par cable, avec son amont (tenant) et son aval (aboutissant),
    reconstruits a partir du graphe amont->aval (voir get_graph()).
    """
    graph = get_graph()
    nodes = {n["id"]: n for n in graph["nodes"]}

    incoming = {}  # cable_tag -> tenant_tag
    outgoing = {}  # cable_tag -> aboutissant_tag
    for e in graph["edges"]:
        if nodes.get(e["to"], {}).get("type") == "cable":
            incoming[e["to"]] = e["from"]
        if nodes.get(e["from"], {}).get("type") == "cable":
            outgoing[e["from"]] = e["to"]

    cable_rows = {r["tag_id"]: r for r in list_rows("cable")}

    schedule = []
    for cable_tag, cable_row in cable_rows.items():
        tenant = incoming.get(cable_tag)
        aboutissant = outgoing.get(cable_tag)
        tenant_node = nodes.get(tenant)
        about_node = nodes.get(aboutissant)
        schedule.append({
            "tenant": tenant or "(non rattache)",
            "type_origine": TYPE_LABELS.get(tenant_node["type"], tenant_node["type"]) if tenant_node else "",
            "aboutissant": aboutissant or "(non rattache)",
            "type_destination": TYPE_LABELS.get(about_node["type"], about_node["type"]) if about_node else "",
            "designation": (about_node.get("detail") or "") if about_node and about_node["type"] == "charge" else "",
            "type_cable": cable_row.get("type") or "",
            "section": cable_row.get("section") or "",
            "longueur_m": cable_row.get("longueur_m"),
            "protection_modele": cable_row.get("protection_modele") or "",
            "calibre_a": cable_row.get("calibre_a"),
            "differentiel_ma": cable_row.get("differentiel_ma"),
        })
    schedule.sort(key=lambda r: (r["tenant"], r["aboutissant"]))
    return schedule


def get_export_schema():
    """
    Derive une description generique du schema (colonnes + relations) a
    partir de TABLES, utilisee pour les exports SQL / Access (avec relations).
    """
    tables = {}
    relationships = []
    for table_name, cfg in TABLES.items():
        cols = []
        for col in cfg["columns"]:
            sql_type = "REAL" if col["type"] == "number" else "TEXT"
            cols.append({"name": col["name"], "sql_type": sql_type, "pk": bool(col.get("pk"))})
        tables[table_name] = {"columns": cols, "pk": cfg["pk"]}
        for col_name, ref_table in cfg.get("fk", {}).items():
            ref_pk = TABLES[ref_table]["pk"][0]
            relationships.append({
                "name": f"fk_{table_name}_{col_name}",
                "table": table_name, "column": col_name,
                "ref_table": ref_table, "ref_column": ref_pk,
            })
    return {"tables": tables, "relationships": relationships}


def build_sql_export():
    """
    Script SQL (CREATE TABLE + cles etrangeres + INSERT) permettant de
    recreer l'integralite du projet actif, relations comprises, dans
    n'importe quel SGBD compatible SQL standard (dont Microsoft Access via
    la fenetre "Creer > Requete > Mode SQL").
    """
    schema = get_export_schema()
    conn = get_connection()
    lines = [
        "-- Export NormaGrid -- script SQL avec relations",
        "-- A executer dans Access via : Creer > Conception de requete > Fermer > Mode SQL",
        "",
    ]

    for table_name, t in schema["tables"].items():
        cols_sql = []
        for c in t["columns"]:
            cols_sql.append(f'  "{c["name"]}" {c["sql_type"]}' + (" NOT NULL" if c["pk"] else ""))
        pk_cols = ", ".join(f'"{c}"' for c in t["pk"])
        lines.append(f'CREATE TABLE "{table_name}" (')
        lines.append(",\n".join(cols_sql) + f',\n  PRIMARY KEY ({pk_cols})')
        lines.append(");")
        lines.append("")

    for rel in schema["relationships"]:
        lines.append(
            f'ALTER TABLE "{rel["table"]}" ADD CONSTRAINT "{rel["name"]}" '
            f'FOREIGN KEY ("{rel["column"]}") REFERENCES "{rel["ref_table"]}" ("{rel["ref_column"]}");'
        )
    lines.append("")

    for table_name in schema["tables"]:
        rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
        for row in rows:
            cols = row.keys()
            vals = []
            for c in cols:
                v = row[c]
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    vals.append("'" + str(v).replace("'", "''") + "'")
            col_list = ", ".join(f'"{c}"' for c in cols)
            lines.append(f'INSERT INTO "{table_name}" ({col_list}) VALUES ({", ".join(vals)});')
    conn.close()
    return "\n".join(lines)


def _compute_bilan_kpis(rows, tension_ht_kv):
    kw_installes = sum(r["puissance_installee"] for r in rows if r.get("puissance_installee") is not None)
    kw_absorbes = sum(r["puissance_active_foisonnee"] for r in rows if r.get("puissance_active_foisonnee") is not None)
    kvar_total = sum(r["puissance_reactive_foisonnee"] for r in rows if r.get("puissance_reactive_foisonnee") is not None)
    kva_reseau = math.sqrt(kw_absorbes ** 2 + kvar_total ** 2)
    cos_phi_global = (kw_absorbes / kva_reseau) if kva_reseau > 0 else None
    i_reseau_hta = (kva_reseau / (math.sqrt(3) * tension_ht_kv)) if (tension_ht_kv and kva_reseau > 0) else None
    return {
        "kw_installes": round(kw_installes, 2),
        "kw_absorbes": round(kw_absorbes, 2),
        "kva_reseau": round(kva_reseau, 2),
        "kvar_total": round(kvar_total, 2),
        "cos_phi_global": round(cos_phi_global, 3) if cos_phi_global is not None else None,
        "i_reseau_hta": round(i_reseau_hta, 1) if i_reseau_hta is not None else None,
    }


def get_bilan_puissance():
    """
    Bilan de puissance : une ligne par charge avec les puissances calculees
    (installee -> active -> apparente/reactive -> foisonnee), et un total
    general en bas (somme des puissances actives/reactives foisonnees).

    Hypotheses de calcul (a valider avec le metier, faute de formule
    explicite dans le principe fourni) :
      - Puissance active unitaire (kW)      = Puissance installee (kW) x Rendement
      - Puissance apparente unitaire (kVA)  = Puissance active unitaire / Cos phi
      - Puissance reactive unitaire (kvar)  = Puissance active unitaire x tan(acos(Cos phi))
      - Puissance active/reactive foisonnee = unitaire x Nombre x K.Util x K.Simul
        (Nombre/K.Util/K.Simul non renseignes -> valeur par defaut 1, pas de derating)
    """
    charges = list_rows("charge")
    rows = []
    total_active_foisonnee = 0.0
    total_reactive_foisonnee = 0.0

    for c in charges:
        installed = c.get("installed_power_kw")
        rendement = c.get("rendement")
        cos_phi = c.get("cos_phi")
        nombre = c.get("nombre") if c.get("nombre") is not None else 1
        k_util = c.get("k_util") if c.get("k_util") is not None else 1
        k_simul = c.get("k_simul") if c.get("k_simul") is not None else 1

        p_active_unit = installed * rendement if installed is not None and rendement is not None else None
        p_apparente_unit = (p_active_unit / cos_phi) if p_active_unit is not None and cos_phi else None
        p_reactive_unit = (p_active_unit * math.tan(math.acos(cos_phi))) if (
            p_active_unit is not None and cos_phi and -1 <= cos_phi <= 1) else None

        p_active_fois = (p_active_unit * nombre * k_util * k_simul) if p_active_unit is not None else None
        p_reactive_fois = (p_reactive_unit * nombre * k_util * k_simul) if p_reactive_unit is not None else None

        if p_active_fois is not None:
            total_active_foisonnee += p_active_fois
        if p_reactive_fois is not None:
            total_reactive_foisonnee += p_reactive_fois

        rows.append({
            "tag_id": c["tag_id"],
            "designation": c.get("equipment_name"),
            "switchgear_mcc": c.get("switchgear_mcc"),
            "equipment_tag_no": c.get("equipment_tag_no"),
            "e_ne": c.get("e_ne"),
            "pct_e": c.get("pct_e"),
            "type_equipement": c.get("type_equipement"),
            "c_i": c.get("c_i"),
            "w_s": c.get("w_s"),
            "puissance_apparente_unitaire": p_apparente_unit,
            "puissance_installee": installed,
            "unite": c.get("unite"),
            "rendement": rendement,
            "puissance_active_unitaire": p_active_unit,
            "nombre": c.get("nombre"),
            "cos_phi": cos_phi,
            "puissance_reactive_unitaire": p_reactive_unit,
            "k_util": c.get("k_util"),
            "k_simul": c.get("k_simul"),
            "puissance_active_foisonnee": p_active_fois,
            "puissance_reactive_foisonnee": p_reactive_fois,
            "alimentation": c.get("voltage"),
        })

    # Tension HT utilisee pour le courant reseau : s'il y a plusieurs reseaux
    # HT dans le projet, on prend le premier (limite connue, a signaler).
    reseaux_ht = list_rows("reseau_ht")
    tension_ht_kv = reseaux_ht[0]["tension_kv"] if reseaux_ht and reseaux_ht[0].get("tension_kv") else None

    return {
        "rows": rows,
        "total_active_foisonnee": round(total_active_foisonnee, 3),
        "total_reactive_foisonnee": round(total_reactive_foisonnee, 3),
        "tension_ht_kv": tension_ht_kv,
    }


def get_tree():
    """
    Hierarchie organisationnelle Client -> Projet -> Site, pour le panneau
    d'arborescence de la vue "Liste des equipements".
    Note : site.client_tag reference en realite projet.tag (nommage
    historique conserve depuis le schema d'origine).
    """
    conn = get_connection()
    clients = conn.execute("SELECT tag, nom FROM client").fetchall()
    projets = conn.execute("SELECT tag, nom, client_tag FROM projet").fetchall()
    sites = conn.execute("SELECT tag, nom, client_tag FROM site").fetchall()
    conn.close()

    tree = []
    for c in clients:
        c_node = {"tag": c["tag"], "nom": c["nom"], "kind": "client", "children": []}
        for p in projets:
            if p["client_tag"] != c["tag"]:
                continue
            p_node = {"tag": p["tag"], "nom": p["nom"], "kind": "projet", "children": []}
            for s in sites:
                if s["client_tag"] == p["tag"]:
                    p_node["children"].append(
                        {"tag": s["tag"], "nom": s["nom"], "kind": "site", "children": []}
                    )
            c_node["children"].append(p_node)
        tree.append(c_node)
    return tree


def get_graph():
    """
    Reconstruit le graphe d'alimentation electrique (qui alimente quoi) a
    partir des colonnes amont_id (transfos/cable/charge) et de la table
    tableau_jointure (amonts multiples pour un tableau).
    Un noeud = un equipement qui existe encore dans sa table source. Une
    arete = amont -> aval.  Le registre `tag` est volontairement ignore pour
    creer les noeuds : il peut conserver un tag pour respecter une cle
    etrangere apres suppression d'un equipement, sans que cet ancien tag
    doive rester visible dans le synoptique.
    """
    conn = get_connection()

    nodes = {}

    detail_queries = {
        "tableaux": "SELECT tag_id AS id, site_id, type AS detail FROM tableaux",
        "transfos": "SELECT tag_id AS id, site_id, puissance_kva AS detail FROM transfos",
        "groupes_electrogenes": "SELECT tag_id AS id, site_id, puissance_kva AS detail FROM groupes_electrogenes",
        "reseau_ht": "SELECT tag_id AS id, site_id, nom AS detail FROM reseau_ht",
        "cable": "SELECT tag_id AS id, site_id, type AS detail FROM cable",
        "charge": "SELECT tag_id AS id, site_id, type AS detail FROM charge",
    }
    for table, query in detail_queries.items():
        for row in conn.execute(query).fetchall():
            nodes[row["id"]] = {
                "id": row["id"],
                "type": table,
                "site_id": row["site_id"],
                "detail": row["detail"],
            }

    edges = []
    edge_keys = set()

    def add_edge(source, target):
        if source in nodes and target in nodes and (source, target) not in edge_keys:
            edge_keys.add((source, target))
            edges.append({"from": source, "to": target})

    for table in ("tableaux", "transfos", "cable", "charge"):
        rows = conn.execute(
            f"SELECT tag_id, amont_id FROM {table} WHERE amont_id IS NOT NULL"
        ).fetchall()
        for r in rows:
            add_edge(r["amont_id"], r["tag_id"])

    for r in conn.execute("SELECT tableau_tag, amont_tag FROM tableau_jointure").fetchall():
        add_edge(r["amont_tag"], r["tableau_tag"])

    conn.close()
    return {"nodes": list(nodes.values()), "edges": edges}


def get_row(table, pk_values):
    cfg = TABLES[table]
    cols = ", ".join(c["name"] for c in cfg["columns"])
    pk_cols = cfg["pk"]
    where = " AND ".join(f"{c} = ?" for c in pk_cols)
    conn = get_connection()
    row = conn.execute(f"SELECT {cols} FROM {table} WHERE {where}", pk_values).fetchone()
    conn.close()
    return dict(row) if row else None


def update_row(table, pk_values, data):
    cfg = TABLES[table]
    col_names = [c["name"] for c in cfg["columns"]]
    pk_cols = cfg["pk"]
    values = {c: data.get(c) or None for c in col_names}

    conn = get_connection()
    try:
        auto_type = cfg.get("auto_tag_type")
        if auto_type:
            pk_col = pk_cols[0]
            conn.execute(
                "INSERT INTO tag (tag, type) VALUES (?, ?) "
                "ON CONFLICT(tag) DO UPDATE SET type=excluded.type",
                (values[pk_col], auto_type),
            )
        set_clause = ", ".join(f"{c} = ?" for c in col_names if c not in pk_cols)
        set_cols = [c for c in col_names if c not in pk_cols]
        where = " AND ".join(f"{c} = ?" for c in pk_cols)
        conn.execute(
            f"UPDATE {table} SET {set_clause} WHERE {where}",
            [values[c] for c in set_cols] + list(pk_values),
        )
        conn.commit()
    finally:
        conn.close()


def import_caneco_with_overrides(analysis, reseau_ht_tag, amont_overrides, include_charges=False):
    """
    Variante de import_caneco_analysis utilisee par le flux d'import en 2
    etapes (apercu puis confirmation) : la correspondance amont est fournie
    explicitement par l'utilisateur (amont_overrides: {tableau: valeur}),
    au lieu d'etre entierement deduite automatiquement. Valeurs possibles :
    "__RESEAU_HT__" (rattache au reseau HT choisi), "__AUCUN__" (source
    autonome, ex: groupe electrogene), ou le nom d'un autre tableau.
    Les charges (circuits terminaux) ne sont importees que si include_charges
    est vrai (choix de l'utilisateur, decoche par defaut).
    """
    reseau = get_row("reseau_ht", [reseau_ht_tag])
    if not reseau:
        raise ValueError("Reseau HT introuvable dans ce projet")
    site_id = reseau["site_id"]

    report = {
        "tableaux": 0, "transfos": 0, "groupes_electrogenes": 0,
        "cables": 0, "charges": 0, "warnings": [],
    }

    boards = analysis["boards"]
    board_types = analysis["board_types"]
    circuits_by_board = analysis["circuits_by_board"]

    conn = get_connection()
    existing_tags = {r["tag"] for r in conn.execute("SELECT tag FROM tag").fetchall()}
    conn.close()

    def unique_tag(base):
        base = re.sub(r"\s+", " ", base).strip()
        if base not in existing_tags:
            existing_tags.add(base)
            return base
        i = 2
        while f"{base} ({i})" in existing_tags:
            i += 1
        final = f"{base} ({i})"
        existing_tags.add(final)
        return final

    # 1) creer toutes les entrees "tableau" (tableaux / transfos / groupes) ---
    board_tag_map = {}
    for b in boards:
        t = board_types[b]
        tag = unique_tag(b)
        board_tag_map[b] = tag
        if t == "tableaux":
            insert_row("tableaux", {"tag_id": tag, "site_id": site_id, "type": "Import Caneco", "tension_v": None})
            report["tableaux"] += 1
        elif t == "transfos":
            insert_row("transfos", {"tag_id": tag, "site_id": site_id, "amont_id": None, "puissance_kva": None})
            report["transfos"] += 1
        elif t == "groupes_electrogenes":
            insert_row("groupes_electrogenes", {"tag_id": tag, "site_id": site_id, "puissance_kva": None})
            report["groupes_electrogenes"] += 1

    def find_circuit(amont_board, dest_board):
        for c in circuits_by_board.get(amont_board, []):
            repere = (c.get("repere") or "").strip()
            if repere and caneco_import.normalize_board_name(repere) == caneco_import.normalize_board_name(dest_board):
                return c
        return None

    def link_board(board, amont_value):
        board_tag = board_tag_map[board]

        if board_types[board] == "groupes_electrogenes":
            report["warnings"].append(
                f"\"{board}\" est un groupe electrogene : le schema ne prevoit pas de colonne "
                "amont pour ce type, le lien choisi n'a pas pu etre enregistre."
            )
            return

        source_circuit = None
        for c in circuits_by_board.get(board, []):
            if (c.get("repere") or "").strip().upper() == "SOURCE":
                source_circuit = c
                break

        if amont_value == "__RESEAU_HT__" and source_circuit and board_types[board] != "groupes_electrogenes":
            transfo_tag = unique_tag(f"{board} - Transfo arrivee")
            insert_row("transfos", {
                "tag_id": transfo_tag, "site_id": site_id, "amont_id": reseau_ht_tag,
                "puissance_kva": caneco_import.parse_power_kva(source_circuit.get("consommation")),
            })
            report["transfos"] += 1
            cable_tag = unique_tag(f"{board} - SOURCE (cable)")
            insert_row("cable", {
                "tag_id": cable_tag, "site_id": site_id, "amont_id": transfo_tag,
                "type": source_circuit.get("cable_type") or None,
                "section": source_circuit.get("cable_section") or None,
                "longueur_m": caneco_import.parse_length_m(source_circuit.get("longueur")),
                "protection_modele": source_circuit.get("protection_modele") or None,
                "calibre_a": source_circuit.get("calibre_a"), "differentiel_ma": source_circuit.get("differentiel_ma"),
            })
            report["cables"] += 1
            amont_for_link = cable_tag
        elif amont_value == "__RESEAU_HT__":
            amont_for_link = reseau_ht_tag
        else:
            amont_board_tag = board_tag_map.get(amont_value)
            if not amont_board_tag:
                report["warnings"].append(f"Amont choisi introuvable pour \"{board}\" : \"{amont_value}\" ignore.")
                return
            circuit = find_circuit(amont_value, board)
            cable_tag = unique_tag(f"{amont_value} - {board} (cable)")
            cable_type = None
            cable_section = None
            longueur_m = None
            protection_modele = None
            calibre_a = None
            differentiel_ma = None
            if circuit:
                cable_type = circuit.get("cable_type") or None
                cable_section = circuit.get("cable_section") or None
                longueur_m = caneco_import.parse_length_m(circuit.get("longueur"))
                protection_modele = circuit.get("protection_modele") or None
                calibre_a = circuit.get("calibre_a")
                differentiel_ma = circuit.get("differentiel_ma")
            insert_row("cable", {
                "tag_id": cable_tag, "site_id": site_id, "amont_id": amont_board_tag,
                "type": cable_type, "section": cable_section, "longueur_m": longueur_m,
                "protection_modele": protection_modele,
                "calibre_a": calibre_a, "differentiel_ma": differentiel_ma,
            })
            report["cables"] += 1
            amont_for_link = cable_tag

        if board_types[board] == "tableaux":
            insert_row("tableau_jointure", {"tableau_tag": board_tag, "amont_tag": amont_for_link,
                                             "protection_modele": None, "calibre_a": None, "differentiel_ma": None})
        elif board_types[board] == "transfos":
            current = get_row("transfos", [board_tag])
            if current:
                current["amont_id"] = amont_for_link
                update_row("transfos", [board_tag], current)

    # 2) appliquer la correspondance amont (eventuellement corrigee par l'utilisateur) --
    # amont_overrides: {tableau: [valeur1, valeur2?]} - une liste car un
    # tableau peut avoir plusieurs amonts (Normal + Secours)
    for board in boards:
        values = amont_overrides.get(board) or []
        if isinstance(values, str):
            values = [values]
        for value in values:
            if value in (None, "", "__AUCUN__"):
                continue
            link_board(board, value)

    # 3) SECOURS : amont supplementaire (un tableau peut avoir plusieurs amonts) --
    for board, circuits in circuits_by_board.items():
        board_tag = board_tag_map.get(board)
        if not board_tag or board_types[board] == "groupes_electrogenes":
            continue
        for c in circuits:
            repere = (c.get("repere") or "").strip()
            if repere.upper() != "SECOURS":
                continue
            ge_tag = unique_tag(repere)
            insert_row("groupes_electrogenes", {
                "tag_id": ge_tag, "site_id": site_id,
                "puissance_kva": caneco_import.parse_power_kva(c.get("consommation")),
            })
            report["groupes_electrogenes"] += 1
            cable_tag = unique_tag(f"{board} - {repere} (cable)")
            insert_row("cable", {
                "tag_id": cable_tag, "site_id": site_id, "amont_id": ge_tag,
                "type": c.get("cable_type") or None,
                "section": c.get("cable_section") or None,
                "longueur_m": caneco_import.parse_length_m(c.get("longueur")),
                "protection_modele": c.get("protection_modele") or None,
                "calibre_a": c.get("calibre_a"), "differentiel_ma": c.get("differentiel_ma"),
            })
            report["cables"] += 1
            if board_types[board] == "tableaux":
                insert_row("tableau_jointure", {"tableau_tag": board_tag, "amont_tag": cable_tag,
                                                 "protection_modele": None, "calibre_a": None, "differentiel_ma": None})
            elif board_types[board] == "transfos":
                current = get_row("transfos", [board_tag])
                if current:
                    current["amont_id"] = cable_tag
                    update_row("transfos", [board_tag], current)

    # 4) charges (circuits terminaux), uniquement si l'utilisateur l'a choisi --
    if include_charges:
        declared_amonts = analysis.get("declared_amonts", {})
        for board, circuits in circuits_by_board.items():
            board_tag = board_tag_map.get(board)
            if not board_tag:
                continue
            own_declared = declared_amonts.get(board, set())
            for c in circuits:
                repere = (c.get("repere") or "").strip()
                if not repere:
                    continue
                norm_repere = caneco_import.normalize_board_name(repere)
                if norm_repere == caneco_import.normalize_board_name(board):
                    continue  # auto-reference (coupleur)
                if norm_repere in own_declared:
                    continue  # reflet de l'amont declare (convention Caneco)
                if repere.upper() in ("SOURCE", "SECOURS"):
                    continue  # deja traites specifiquement plus haut
                if any(caneco_import.normalize_board_name(b) == norm_repere for b in boards):
                    continue  # c'est un tableau connu, pas une charge

                cable_tag = unique_tag(f"{board} - {repere} (cable)")
                insert_row("cable", {
                    "tag_id": cable_tag, "site_id": site_id, "amont_id": board_tag,
                    "type": c.get("cable_type") or None,
                    "section": c.get("cable_section") or None,
                    "longueur_m": caneco_import.parse_length_m(c.get("longueur")),
                    "protection_modele": c.get("protection_modele") or None,
                    "calibre_a": c.get("calibre_a"), "differentiel_ma": c.get("differentiel_ma"),
                })
                report["cables"] += 1

                charge_tag = unique_tag(repere)
                cable_label = " ".join(filter(None, [c.get("cable_type"), c.get("cable_section")])).strip()
                charge_type = c.get("designation") or cable_label or "Charge importee"
                insert_row("charge", {
                    "tag_id": charge_tag, "site_id": site_id, "amont_id": cable_tag,
                    "type": charge_type,
                    "protection_modele": c.get("protection_modele") or None,
                    "calibre_a": c.get("calibre_a"), "differentiel_ma": c.get("differentiel_ma"),
                })
                report["charges"] += 1

    return report



def delete_row(table, pk_values):
    cfg = TABLES[table]
    pk_cols = cfg["pk"]
    where = " AND ".join(f"{c} = ?" for c in pk_cols)
    conn = get_connection()
    try:
        conn.execute(f"DELETE FROM {table} WHERE {where}", pk_values)
        conn.commit()
    finally:
        conn.close()
