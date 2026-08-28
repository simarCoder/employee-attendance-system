import threading
import time

import webview
from werkzeug.serving import make_server

from backend.app import app


HOST = "127.0.0.1"
PORT = 5000


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

    # Start Flask in background
    flask_thread = threading.Thread(
        target=start_server,
        daemon=True,
    )

    flask_thread.start()

    # Give Flask a moment to start
    time.sleep(1)

    # Create desktop window
    window = webview.create_window(
        "HR Management System | Operon Solutions",
        f"http://{HOST}:{PORT}/",
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