"""Desktop launcher for the packaged Windows build.

Double-click the exe (or run it from a console). It starts the local Flask
server on a free port, opens the default browser, and keeps running until the
console window is closed.
"""
from __future__ import annotations

import os
import socket
import threading
import webbrowser

from werkzeug.serving import make_server

from app import app
from evalapp.paths import HOME_ROOT, seed_home


def _free_port(preferred: int = 5051) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    seed_home()
    port = int(os.environ.get("PORT", "0") or "0") or _free_port()
    url = f"http://127.0.0.1:{port}"
    server = make_server("127.0.0.1", port, app, threaded=True)

    print()
    print("  Activity Eval Studio")
    print("  --------------------")
    print(f"  Open:  {url}")
    print(f"  Data:  {HOME_ROOT}")
    print("  Close this window to stop the local server.")
    print()

    if os.environ.get("ACTIVITY_EVAL_NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
