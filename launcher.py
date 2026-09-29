import threading
import time
import sys

import webview
from werkzeug.serving import make_server

from backend.app import app
from updater import get_available_release, make_update_prompt


HOST = "127.0.0.1"
PORT = 5000

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

    # Give Flask a moment to start
    time.sleep(1)

    main_url = f"http://{HOST}:{PORT}/"
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
        )
        update_api.window = window
        window.events.closing += update_api.on_window_closing
        webview.start(debug=False)
    else:
        window = webview.create_window(
            title,
            main_url,
            width=1400,
            height=900,
            min_size=(1000, 700),
            resizable=True,
        )
        webview.start(
            func=lambda: window.maximize(),
            debug=False,
        )

    close_application()
    
    
    
# BUILDING COMMAND FOR SPEC FILE -  python -m PyInstaller HR_Management_System.spec
