import os

from flask import Flask, render_template, jsonify
from backend.db import init_db, NoActiveProject
from backend.routes.api import api
from backend.routes.projects import projects_bp

APP_VERSION = "V1.44"
# Render renseigne cet identifiant a chaque commit deployee. Il evite que le
# navigateur reutilise un ancien CSS/JS apres un redeploiement.
ASSET_VERSION = os.environ.get("RENDER_GIT_COMMIT", APP_VERSION)

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # evite que le navigateur garde en cache un ancien JS/CSS
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.register_blueprint(api)
app.register_blueprint(projects_bp)

# Gunicorn importe ce module sans executer le bloc __main__. Initialiser ici
# garantit qu'un projet SQLite actif existe egalement sur Render.
init_db()


@app.errorhandler(NoActiveProject)
def handle_no_active_project(e):
    return jsonify({"error": "no_active_project", "message": "Aucun projet n'est ouvert."}), 409


@app.get("/")
def index():
    return render_template(
        "index.html",
        version=APP_VERSION,
        asset_version=ASSET_VERSION,
    )


@app.get("/health")
def health():
    """Point de controle utilise par Render pour verifier le service."""
    return {"status": "ok", "version": APP_VERSION}


if __name__ == "__main__":
    print(f"=== NormaGrid {APP_VERSION} ===")
    try:
        app.run(
            debug=os.environ.get("FLASK_DEBUG") == "1",
            host="0.0.0.0",
            port=int(os.environ.get("PORT", "5000")),
        )
    except OSError as e:
        print("\nERREUR : le port 5000 est deja utilise par un autre programme.")
        print("Fermez toute fenetre/terminal ou un ancien 'python app.py' tournerait encore,")
        print("puis relancez ce script.\n")
        raise e
