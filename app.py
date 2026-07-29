from flask import Flask, render_template, jsonify
from backend.db import init_db, NoActiveProject
from backend.routes.api import api
from backend.routes.projects import projects_bp

APP_VERSION = "V1.44"

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # evite que le navigateur garde en cache un ancien JS/CSS
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.register_blueprint(api)
app.register_blueprint(projects_bp)


@app.errorhandler(NoActiveProject)
def handle_no_active_project(e):
    return jsonify({"error": "no_active_project", "message": "Aucun projet n'est ouvert."}), 409


@app.get("/")
def index():
    return render_template("index.html", version=APP_VERSION)


if __name__ == "__main__":
    init_db()
    print(f"=== NormaGrid {APP_VERSION} ===")
    try:
        app.run(debug=True, host="0.0.0.0", port=5000)
    except OSError as e:
        print("\nERREUR : le port 5000 est deja utilise par un autre programme.")
        print("Fermez toute fenetre/terminal ou un ancien 'python app.py' tournerait encore,")
        print("puis relancez ce script.\n")
        raise e
