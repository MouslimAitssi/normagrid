"""
Point d'entree "application de bureau" : lance Flask en arriere-plan et
affiche l'interface dans une fenetre native (pywebview) au lieu d'un onglet
de navigateur. Cela permet d'exposer de vraies boites de dialogue natives
(choisir un dossier / un fichier) via le pont js_api, ce qu'une page web
ouverte dans un navigateur classique ne peut pas faire pour des raisons de
securite (le navigateur ne revele jamais le chemin reel du disque).
"""

import threading
import webview

from app import app, APP_VERSION
from backend.db import init_db

HOST = "127.0.0.1"
PORT = 5000


class Api:
    """Methodes exposees a la page (window.pywebview.api.<methode>)."""

    def choose_folder(self):
        window = webview.windows[0]
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    def choose_db_file(self, mode="open"):
        window = webview.windows[0]
        file_types = ("Fichiers NormaGrid (*.db)", "Tous les fichiers (*.*)")
        dialog_type = webview.SAVE_DIALOG if mode == "save" else webview.OPEN_DIALOG
        result = window.create_file_dialog(dialog_type, file_types=file_types)
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result


def _run_flask():
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    init_db()
    print(f"=== NormaGrid {APP_VERSION} (application de bureau) ===")

    flask_thread = threading.Thread(target=_run_flask, daemon=True)
    flask_thread.start()

    api = Api()
    webview.create_window(
        f"NormaGrid {APP_VERSION}",
        f"http://{HOST}:{PORT}",
        js_api=api,
        width=1440,
        height=920,
        min_size=(1100, 700),
    )
    webview.start()
