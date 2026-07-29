import os
import tempfile
import uuid

from flask import Blueprint, jsonify, request
from backend import db

projects_bp = Blueprint("projects", __name__, url_prefix="/api/projects")


@projects_bp.get("/default-folder")
def default_folder():
    return jsonify({"folder": db.PROJECTS_DIR})


@projects_bp.get("/export-accdb-available")
def export_accdb_available():
    from backend import access_export
    return jsonify({"available": access_export.is_available()})


@projects_bp.post("/export-sql")
def export_sql():
    from backend import models

    if not db.get_active_project():
        return jsonify({"error": "Ouvrez ou creez un projet avant d'exporter."}), 409

    data = request.get_json(force=True) or {}
    folder = (data.get("folder") or "").strip()
    filename = (data.get("filename") or "").strip()
    if not folder:
        return jsonify({"error": "Le dossier de destination est obligatoire."}), 400
    if not filename:
        return jsonify({"error": "Le nom du fichier est obligatoire."}), 400
    if not filename.lower().endswith(".sql"):
        filename += ".sql"

    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as e:
        return jsonify({"error": f"Impossible de creer/acceder au dossier : {e}"}), 400

    full_path = os.path.join(folder, filename)
    try:
        sql_text = models.build_sql_export()
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(sql_text)
    except OSError as e:
        return jsonify({"error": f"Impossible d'ecrire le fichier : {e}"}), 400

    return jsonify({"ok": True, "path": full_path}), 201


@projects_bp.post("/export-accdb")
def export_accdb():
    from backend import models, access_export

    active = db.get_active_project()
    if not active:
        return jsonify({"error": "Ouvrez ou creez un projet avant d'exporter."}), 409

    data = request.get_json(force=True) or {}
    folder = (data.get("folder") or "").strip()
    filename = (data.get("filename") or "").strip()
    if not folder:
        return jsonify({"error": "Le dossier de destination est obligatoire."}), 400
    if not filename:
        return jsonify({"error": "Le nom du fichier est obligatoire."}), 400
    if not filename.lower().endswith(".accdb"):
        filename += ".accdb"

    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as e:
        return jsonify({"error": f"Impossible de creer/acceder au dossier : {e}"}), 400

    full_path = os.path.join(folder, filename)
    schema = models.get_export_schema()
    try:
        warnings = access_export.export_to_accdb(active, full_path, schema)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Erreur inattendue lors de l'export .accdb : {e}"}), 500

    return jsonify({"ok": True, "path": full_path, "warnings": warnings}), 201


@projects_bp.get("")
def list_projects():
    return jsonify({
        "projects": db.list_projects(),
        "active": db.get_active_project(),
    })


@projects_bp.post("/new")
def new_project():
    data = request.get_json(force=True)
    name = (data or {}).get("name", "").strip()
    folder = (data or {}).get("folder", "").strip() or None
    if not name:
        return jsonify({"error": "Le nom du projet est requis"}), 400
    try:
        path = db.create_project(name, folder)
    except (ValueError, OSError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "path": path}), 201


@projects_bp.post("/open")
def open_project():
    data = request.get_json(force=True)
    path = (data or {}).get("path", "").strip()
    if not path:
        return jsonify({"error": "Le chemin du fichier est requis"}), 400
    try:
        db.open_project(path)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


@projects_bp.post("/close")
def close_project():
    db.close_project()
    return jsonify({"ok": True})


@projects_bp.post("/save-as")
def save_as():
    data = request.get_json(force=True)
    name = (data or {}).get("name", "").strip()
    folder = (data or {}).get("folder", "").strip() or None
    if not name:
        return jsonify({"error": "Le nom du projet est requis"}), 400
    try:
        path = db.save_project_as(name, folder)
    except (ValueError, OSError, db.NoActiveProject) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "path": path}), 201


@projects_bp.post("/import-normagrid")
def import_normagrid():
    """Import reel : un fichier .db d'une ancienne version de NormaGrid devient un nouveau projet."""
    if not db.get_active_project():
        return jsonify({"error": "Ouvrez ou creez un projet avant de faire un import."}), 409

    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier recu"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Aucun fichier recu"}), 400

    project_name = request.form.get("name", "").strip()
    if not project_name:
        project_name = os.path.splitext(os.path.basename(file.filename))[0]
    folder = request.form.get("folder", "").strip() or None

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        path = db.import_project_file(tmp_path, project_name, folder)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return jsonify({"ok": True, "path": path}), 201


# --- Import Excel : entree de menu prevue, traitement a venir ---
def _normalize_col(s):
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", s.strip().lower())


@projects_bp.post("/import-caneco/staging-analyze")
def import_caneco_staging_analyze():
    """Etape 1 (table de preparation) : extrait tous les circuits bruts du
    PDF, sans rien ecrire en base. L'utilisateur pourra tout modifier avant
    de confirmer le chargement dans import_caneco_staging."""
    from backend import caneco_import

    if not db.get_active_project():
        return jsonify({"error": "Ouvrez ou creez un projet avant de faire un import."}), 409

    if "file" not in request.files or not request.files["file"].filename:
        return jsonify({"error": "Aucun fichier PDF recu"}), 400
    file = request.files["file"]

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        rows = caneco_import.extract_all_staging_rows(tmp_path)
    except Exception as e:
        return jsonify({"error": f"Erreur lors de l'analyse du PDF : {e}"}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return jsonify({"rows": rows, "nb_rows": len(rows)})


@projects_bp.post("/import-caneco/staging-confirm")
def import_caneco_staging_confirm():
    """Etape 2 (table de preparation) : ecrit les lignes (eventuellement
    corrigees par l'utilisateur) dans la table import_caneco_staging."""
    from backend import models

    if not db.get_active_project():
        return jsonify({"error": "Ouvrez ou creez un projet avant de faire un import."}), 409

    data = request.get_json(force=True) or {}
    rows = data.get("rows") or []
    if not rows:
        return jsonify({"error": "Aucune ligne a charger."}), 400

    fields = [
        "board_repere", "board_designation", "amont_normal", "amont_secours",
        "circuit_repere", "circuit_designation", "nombre", "consommation",
        "alimentation", "jdb_amont", "liaison_type", "longueur", "ame", "l_max_prot",
        "delta_u_circuit", "delta_u_totale", "cable", "neutre", "pe_pen", "separe",
        "taux_harmonique", "protection", "calibre", "i_delta_n", "ir", "im_isd",
        "affectation_phases", "type_detecte",
    ]

    conn = db.get_connection()
    try:
        for row in rows:
            values = [row.get(f) for f in fields]
            placeholders = ", ".join("?" for _ in fields)
            col_list = ", ".join(fields)
            conn.execute(f"INSERT INTO import_caneco_staging ({col_list}) VALUES ({placeholders})", values)
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({"error": f"Erreur lors du chargement : {e}"}), 500
    conn.close()

    return jsonify({"ok": True, "nb_rows": len(rows)}), 201


@projects_bp.get("/import-caneco/staging-rows")
def import_caneco_staging_rows():
    """Consultation de la table de preparation deja chargee (pour verification)."""
    if not db.get_active_project():
        return jsonify({"error": "Aucun projet ouvert."}), 409
    conn = db.get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM import_caneco_staging ORDER BY id").fetchall()]
    conn.close()
    return jsonify({"rows": rows, "nb_rows": len(rows)})


@projects_bp.get("/import-caneco/staging-preview")
def import_caneco_staging_preview():
    """Etape 3 (conversion) : reconstruit, a partir des lignes NON ENCORE
    CONVERTIES de la table de preparation (sans re-parser le PDF), un
    apercu de la hierarchie tableaux/transfos/groupes avec des amonts
    proposes par defaut -- modifiable par l'utilisateur avant confirmation.
    Aucune ecriture en base a cette etape."""
    from backend import caneco_import

    if not db.get_active_project():
        return jsonify({"error": "Ouvrez ou creez un projet avant de faire un import."}), 409

    conn = db.get_connection()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM import_caneco_staging WHERE converti = 0 ORDER BY id"
    ).fetchall()]
    conn.close()

    if not rows:
        return jsonify({"boards": [], "nb_rows": 0})

    analysis = caneco_import.build_analysis_from_staging_rows(rows)
    return jsonify({"boards": analysis["boards_preview"], "nb_rows": len(rows)})


@projects_bp.post("/import-caneco/staging-convert")
def import_caneco_staging_convert():
    """Etape 4 (conversion) : cree reellement les tableaux/transfos/groupes
    electrogenes/cables (et optionnellement les charges) a partir des
    lignes NON ENCORE CONVERTIES de la table de preparation, avec la
    correspondance amont eventuellement corrigee par l'utilisateur a
    l'etape d'apercu. Marque ensuite ces lignes comme converties."""
    from backend import models, caneco_import

    if not db.get_active_project():
        return jsonify({"error": "Ouvrez ou creez un projet avant de faire un import."}), 409

    data = request.get_json(force=True) or {}
    reseau_ht_tag = (data.get("reseau_ht_tag") or "").strip()
    amonts = data.get("amonts") or {}
    include_charges = bool(data.get("include_charges", False))

    if not reseau_ht_tag:
        return jsonify({"error": "Reseau HT de rattachement manquant."}), 400

    conn = db.get_connection()
    staging_rows = [dict(r) for r in conn.execute(
        "SELECT * FROM import_caneco_staging WHERE converti = 0 ORDER BY id"
    ).fetchall()]

    if not staging_rows:
        conn.close()
        return jsonify({"error": "Aucune ligne a convertir : importez d'abord une note de calcul Caneco, "
                                  "ou toutes les lignes existantes ont deja ete converties."}), 409

    try:
        analysis = caneco_import.build_analysis_from_staging_rows(staging_rows)
        report = models.import_caneco_with_overrides(analysis, reseau_ht_tag, amonts, include_charges)
    except ValueError as e:
        conn.close()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        conn.close()
        return jsonify({"error": f"Erreur lors de la conversion : {e}"}), 500

    ids = [r["id"] for r in staging_rows]
    conn.executemany("UPDATE import_caneco_staging SET converti = 1 WHERE id = ?", [(i,) for i in ids])
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "report": report}), 201


@projects_bp.post("/import-excel/analyze")
def import_excel_analyze():
    """Etape 1 : lit l'entete du fichier Excel (lecture seule) et propose
    une correspondance automatique avec les champs de la table charge."""
    from openpyxl import load_workbook
    from backend import models

    if not db.get_active_project():
        return jsonify({"error": "Ouvrez ou creez un projet avant d'importer."}), 409

    reseaux_ht = models.list_rows("reseau_ht")
    if not reseaux_ht:
        return jsonify({"error": "Creez d'abord un reseau HT dans ce projet avant de pouvoir importer."}), 409

    if "file" not in request.files or not request.files["file"].filename:
        return jsonify({"error": "Aucun fichier Excel recu"}), 400
    file = request.files["file"]

    session_dir = os.path.join(db.BASE_DIR, "database", "excel_sessions")
    os.makedirs(session_dir, exist_ok=True)
    session_id = uuid.uuid4().hex
    saved_path = os.path.join(session_dir, f"{session_id}.xlsx")

    try:
        file.save(saved_path)
        wb = load_workbook(saved_path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None)
        if not header:
            raise ValueError("Le fichier est vide (aucune ligne d'entete trouvee).")
        excel_columns = [str(h).strip() if h is not None else "" for h in header]
        excel_columns = [c for c in excel_columns if c]

        preview_rows = []
        for i, row in enumerate(rows_iter):
            if i >= 5:
                break
            preview_rows.append([("" if v is None else str(v)) for v in row[:len(excel_columns)]])

        nb_data_rows = sum(1 for _ in ws.iter_rows(min_row=2, values_only=True) if any(c is not None for c in _))
        wb.close()
    except Exception as e:
        if os.path.exists(saved_path):
            os.remove(saved_path)
        return jsonify({"error": f"Erreur de lecture du fichier Excel : {e}"}), 400

    charge_columns = [c for c in models.TABLES["charge"]["columns"] if c["name"] not in ("site_id",)]
    norm_excel = {_normalize_col(h): h for h in excel_columns}
    suggested_mapping = {}
    for col in charge_columns:
        for candidate in (col["name"], col["label"]):
            norm_cand = _normalize_col(candidate)
            if norm_cand in norm_excel:
                suggested_mapping[col["name"]] = norm_excel[norm_cand]
                break

    return jsonify({
        "session_id": session_id,
        "excel_columns": excel_columns,
        "preview_rows": preview_rows,
        "nb_data_rows": nb_data_rows,
        "charge_columns": [{"name": c["name"], "label": c["label"], "pk": bool(c.get("pk"))} for c in charge_columns],
        "suggested_mapping": suggested_mapping,
        "reseaux_ht": reseaux_ht,
    })


@projects_bp.post("/import-excel/confirm")
def import_excel_confirm():
    """Etape 2 : ecrit reellement les charges en base, selon la
    correspondance de champs validee par l'utilisateur."""
    from openpyxl import load_workbook
    from backend import models

    if not db.get_active_project():
        return jsonify({"error": "Ouvrez ou creez un projet avant d'importer."}), 409

    data = request.get_json(force=True) or {}
    session_id = (data.get("session_id") or "").strip()
    reseau_ht_tag = (data.get("reseau_ht_tag") or "").strip()
    mapping = data.get("mapping") or {}  # {champ_charge: colonne_excel}

    if not session_id:
        return jsonify({"error": "Session d'import expiree, relancez l'analyse."}), 400
    if not reseau_ht_tag:
        return jsonify({"error": "Choisissez le reseau HT de rattachement."}), 400
    if not mapping.get("tag_id"):
        return jsonify({"error": "Le champ Tag doit obligatoirement etre associe a une colonne du fichier."}), 400

    reseau = models.get_row("reseau_ht", [reseau_ht_tag])
    if not reseau:
        return jsonify({"error": "Reseau HT introuvable dans ce projet."}), 400
    site_id = reseau["site_id"]

    session_dir = os.path.join(db.BASE_DIR, "database", "excel_sessions")
    saved_path = os.path.join(session_dir, f"{session_id}.xlsx")
    if not os.path.exists(saved_path):
        return jsonify({"error": "Session d'import expiree, relancez l'analyse."}), 400

    report = {"created": 0, "skipped": 0, "warnings": []}
    try:
        wb = load_workbook(saved_path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None)
        excel_columns = [str(h).strip() if h is not None else "" for h in header]
        col_index = {name: i for i, name in enumerate(excel_columns) if name}

        known_tags = {r["tag"] for r in models.list_rows("tag")}
        charge_cols_by_name = {c["name"]: c for c in models.TABLES["charge"]["columns"]}

        for row in rows_iter:
            if row is None or all(v is None for v in row):
                continue

            def value_for(field):
                col_name = mapping.get(field)
                if not col_name or col_name not in col_index:
                    return None
                idx = col_index[col_name]
                if idx >= len(row):
                    return None
                v = row[idx]
                return None if v is None else v

            tag_id = value_for("tag_id")
            if not tag_id or not str(tag_id).strip():
                report["skipped"] += 1
                continue
            tag_id = str(tag_id).strip()
            if tag_id in known_tags:
                report["warnings"].append(f"\"{tag_id}\" existe deja : ligne ignoree.")
                report["skipped"] += 1
                continue

            payload = {"tag_id": tag_id, "site_id": site_id}
            for field, col_cfg in charge_cols_by_name.items():
                if field in ("tag_id", "site_id"):
                    continue
                v = value_for(field)
                if v is None or v == "":
                    continue
                if col_cfg["type"] == "number":
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        report["warnings"].append(f"\"{tag_id}\" : valeur non numerique ignoree pour {field} ({v!r}).")
                        continue
                elif field == "amont_id":
                    v = str(v).strip()
                    if v not in known_tags:
                        report["warnings"].append(f"\"{tag_id}\" : amont \"{v}\" introuvable, laisse vide.")
                        continue
                else:
                    v = str(v)
                payload[field] = v

            try:
                models.insert_row("charge", payload)
                known_tags.add(tag_id)
                report["created"] += 1
            except Exception as e:
                report["warnings"].append(f"\"{tag_id}\" : erreur a la creation ({e}).")
                report["skipped"] += 1

        wb.close()
    except Exception as e:
        return jsonify({"error": f"Erreur lors de l'import : {e}"}), 500
    finally:
        if os.path.exists(saved_path):
            os.remove(saved_path)

    return jsonify({"ok": True, "report": report}), 201


@projects_bp.post("/import-excel")
def import_excel():
    return jsonify({"error": "not_implemented", "message": "Utilisez le nouveau flux en 2 etapes (analyze/confirm)."}), 501


@projects_bp.post("/import-caneco/analyze")
def import_caneco_analyze():
    """Etape 1 : analyse le PDF (lecture seule) et renvoie un apercu de la
    hierarchie proposee, modifiable par l'utilisateur avant confirmation."""
    from backend import caneco_import

    if not db.get_active_project():
        return jsonify({"error": "Ouvrez ou creez un projet avant de faire un import."}), 409

    if "file" not in request.files or not request.files["file"].filename:
        return jsonify({"error": "Aucun fichier PDF recu"}), 400
    file = request.files["file"]

    session_dir = os.path.join(db.BASE_DIR, "database", "caneco_sessions")
    os.makedirs(session_dir, exist_ok=True)
    session_id = uuid.uuid4().hex
    saved_path = os.path.join(session_dir, f"{session_id}.pdf")

    try:
        file.save(saved_path)
        analysis = caneco_import.analyze_pdf(saved_path)
    except Exception as e:
        if os.path.exists(saved_path):
            os.remove(saved_path)
        return jsonify({"error": f"Erreur lors de l'analyse du PDF : {e}"}), 500

    amont_of = {}
    for src, dst in analysis["edges"]:
        amont_of.setdefault(dst, []).append(src)

    boards_preview = []
    for b in analysis["boards"]:
        proposed = amont_of.get(b, [])
        if not proposed:
            proposed = ["__RESEAU_HT__"] if b in analysis["roots"] and analysis["board_types"][b] != "groupes_electrogenes" else []
        boards_preview.append({"name": b, "type": analysis["board_types"][b], "proposed_amonts": proposed})

    return jsonify({
        "session_id": session_id,
        "boards": boards_preview,
        "nb_pages": analysis["nb_pages"],
        "nb_edges": len(analysis["edges"]),
    })


@projects_bp.post("/import-caneco/confirm")
def import_caneco_confirm():
    """Etape 2 : ecrit reellement en base, en utilisant la correspondance
    amont eventuellement corrigee par l'utilisateur a l'etape d'apercu."""
    from backend import models, caneco_import

    if not db.get_active_project():
        return jsonify({"error": "Ouvrez ou creez un projet avant de faire un import."}), 409

    data = request.get_json(force=True)
    session_id = (data or {}).get("session_id", "").strip()
    reseau_ht_tag = (data or {}).get("reseau_ht_tag", "").strip()
    amonts = (data or {}).get("amonts", {})
    include_charges = bool((data or {}).get("include_charges", False))

    if not reseau_ht_tag:
        return jsonify({"error": "Reseau HT de rattachement manquant."}), 400
    if not session_id:
        return jsonify({"error": "Session d'import expiree, relancez l'analyse."}), 400

    session_dir = os.path.join(db.BASE_DIR, "database", "caneco_sessions")
    saved_path = os.path.join(session_dir, f"{session_id}.pdf")
    if not os.path.exists(saved_path):
        return jsonify({"error": "Session d'import expiree, relancez l'analyse."}), 400

    try:
        analysis = caneco_import.analyze_pdf(saved_path)
        report = models.import_caneco_with_overrides(analysis, reseau_ht_tag, amonts, include_charges)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Erreur lors de l'import : {e}"}), 500
    finally:
        if os.path.exists(saved_path):
            os.remove(saved_path)

    return jsonify({"ok": True, "report": report}), 201


@projects_bp.post("/import-etap")
def import_etap():
    return jsonify({"error": "not_implemented", "message": "Import Etap : prevu dans une prochaine etape."}), 501
