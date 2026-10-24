import os
import socket
import sys
import threading
import time

import webview
from werkzeug.serving import make_server

from backend.app import app
from updater import get_available_release, make_update_prompt


HOST = "0.0.0.0"
PORT = 5000

# Base and persistent storage directories for PyWebView (Edge WebView2)
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WEBVIEW_DATA_DIR = os.path.join(BASE_DIR, "db", "webview_data")
os.makedirs(WEBVIEW_DATA_DIR, exist_ok=True)

# Let PyWebView's native backend handle Flask attachment responses (PDFs) and
# show its normal Save dialog instead of relying on browser blob downloads.
webview.settings["ALLOW_DOWNLOADS"] = True


class FlaskServer:
    def __init__(self, flask_app, host, port):
        self.app = flask_app
        self.host = host
        self.port = port
        self.server = None

    def start(self):
        self.server = make_server(
            self.host,
            self.port,
            self.app,
            threaded=True,
        )

        self.server.serve_forever()

    def shutdown(self):
        if self.server:
            self.server.shutdown()


server = FlaskServer(app, HOST, PORT)


def start_server():
    server.start()


def wait_for_server(host, port, timeout=4.0):
    """
    Poll the server port non-blockingly until it accepts connections.
    Saves ~950ms on cold startup compared to static sleep.
    """
    start = time.time()
    target_host = "127.0.0.1" if host == "0.0.0.0" else host
    while time.time() - start < timeout:
        try:
            with socket.create_connection((target_host, port), timeout=0.05):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.015)
    return False


def close_application():
    print("Shutting down Flask server...")

    server.shutdown()

    print("Flask server stopped.")


if __name__ == "__main__":

    # Check published releases before opening the desktop application. The
    # update prompt transitions into the app in the same WebView if deferred.
    release = get_available_release() if getattr(sys, "frozen", False) else None

    # Start Flask in background
    flask_thread = threading.Thread(
        target=start_server,
        daemon=True,
    )

    flask_thread.start()

    # Fast dynamic wait instead of static 1-second pause
    wait_for_server(HOST, PORT)

    main_url = f"http://127.0.0.1:{PORT}/"
    title = "HR Management System | Operon Solutions"
    prompt_html, update_api = make_update_prompt(release, main_url) if release else (None, None)

    if prompt_html:
        window = webview.create_window(
            "HR Management System Update",
            html=prompt_html,
            js_api=update_api,
            width=560,
            height=430,
            resizable=False,
            background_color="#000000",
        )
        update_api.window = window
        window.events.closing += update_api.on_window_closing
        webview.start(
            debug=False,
            private_mode=False,
            storage_path=WEBVIEW_DATA_DIR,
        )
    else:
        window = webview.create_window(
            title,
            main_url,
            width=1400,
            height=900,
            min_size=(1000, 700),
            resizable=True,
            background_color="#000000",
        )
        webview.start(
            func=lambda: window.maximize(),
            debug=False,
            private_mode=False,
            storage_path=WEBVIEW_DATA_DIR,
        )

    close_application()
    
    
# BUILDING COMMAND FOR SPEC FILE -  python -m PyInstaller HR_Management_System.spec
