"""
Export direct vers un fichier Microsoft Access (.accdb), relations comprises.

ATTENTION - code non teste par Claude en conditions reelles : cette
fonctionnalite s'appuie sur pywin32 (automatisation COM/ADOX) et pyodbc,
disponibles uniquement sous Windows avec Microsoft Access (ou le moteur
gratuit "Access Database Engine Redistributable") installe. Aucun de ces
composants n'existe dans l'environnement de developpement (Linux) utilise
pour construire ce prototype : ce fichier n'a donc pas pu etre valide en
conditions reelles, contrairement au reste de l'application. Merci de
signaler toute erreur rencontree lors de son utilisation, avec le message
d'erreur complet, pour permettre de corriger le tir.

Principe :
1. Creation d'un fichier .accdb vierge via le moteur ACE (ADOX.Catalog),
   sans avoir besoin d'ouvrir l'application Access elle-meme.
2. Connexion a ce fichier via pyodbc (pilote "Microsoft Access Driver").
3. Creation des tables (CREATE TABLE) et copie des donnees (INSERT).
4. Ajout des relations entre tables (ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY).
"""

import os
import sqlite3


def is_available():
    """True si les composants necessaires (Windows + pywin32 + pyodbc) semblent presents."""
    try:
        import win32com.client  # noqa: F401
        import pyodbc  # noqa: F401
        return True
    except ImportError:
        return False


ACCESS_TYPE = {"TEXT": "TEXT", "REAL": "DOUBLE"}


def export_to_accdb(sqlite_db_path, output_path, schema):
    """
    Cree un nouveau fichier .accdb a l'emplacement voulu, y recree toutes
    les tables du projet (colonnes + cle primaire), y copie les donnees,
    puis ajoute les relations (cles etrangeres).

    Renvoie la liste des relations qui n'ont pas pu etre creees (avec leur
    message d'erreur), le cas echeant : cela peut arriver si des donnees
    orphelines existent (une valeur qui ne correspond a aucune ligne de la
    table referencee), Access refusant alors la contrainte.
    """
    try:
        import win32com.client
        import pyodbc
    except ImportError as e:
        raise RuntimeError(
            "Export .accdb indisponible sur ce poste : necessite pywin32 et pyodbc, "
            f"presents uniquement sous Windows avec Microsoft Access installe ({e})."
        )

    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except OSError as e:
            raise RuntimeError(f"Impossible de remplacer le fichier existant : {e}")

    # 1) Creer un fichier .accdb vierge via le moteur ACE (ADOX)
    catalog = win32com.client.Dispatch("ADOX.Catalog")
    created = False
    last_error = None
    for provider in ("Microsoft.ACE.OLEDB.16.0", "Microsoft.ACE.OLEDB.12.0"):
        try:
            catalog.Create(f"Provider={provider};Data Source={output_path};")
            created = True
            break
        except Exception as e:
            last_error = e
    if not created:
        raise RuntimeError(
            "Impossible de creer le fichier .accdb : le moteur Microsoft ACE "
            "(Access Database Engine) semble absent de ce poste. Installez Microsoft "
            f"Access ou le moteur gratuit 'Access Database Engine Redistributable'. Detail : {last_error}"
        )

    # 2) Se connecter via pyodbc pour creer les tables et inserer les donnees
    conn_str = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + output_path + ";"
    conn = pyodbc.connect(conn_str, autocommit=True)
    cursor = conn.cursor()
    relation_warnings = []

    try:
        for table_name, t in schema["tables"].items():
            cols_sql = [f"[{c['name']}] {ACCESS_TYPE.get(c['sql_type'], 'TEXT')}" for c in t["columns"]]
            pk_cols = ", ".join(f"[{c}]" for c in t["pk"])
            ddl = (
                f"CREATE TABLE [{table_name}] ({', '.join(cols_sql)}, "
                f"CONSTRAINT [pk_{table_name}] PRIMARY KEY ({pk_cols}))"
            )
            cursor.execute(ddl)

        src = sqlite3.connect(sqlite_db_path)
        src.row_factory = sqlite3.Row
        for table_name in schema["tables"]:
            rows = src.execute(f"SELECT * FROM {table_name}").fetchall()
            if not rows:
                continue
            col_names = rows[0].keys()
            col_list = ", ".join(f"[{c}]" for c in col_names)
            placeholders = ", ".join("?" for _ in col_names)
            insert_sql = f"INSERT INTO [{table_name}] ({col_list}) VALUES ({placeholders})"
            for row in rows:
                cursor.execute(insert_sql, tuple(row[c] for c in col_names))
        src.close()

        for rel in schema["relationships"]:
            try:
                ddl = (
                    f"ALTER TABLE [{rel['table']}] ADD CONSTRAINT [{rel['name']}] "
                    f"FOREIGN KEY ([{rel['column']}]) REFERENCES [{rel['ref_table']}] ([{rel['ref_column']}])"
                )
                cursor.execute(ddl)
            except Exception as e:
                relation_warnings.append(f"{rel['name']} : {e}")
    finally:
        cursor.close()
        conn.close()

    return relation_warnings
