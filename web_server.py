"""Run the private local workspace: python web_server.py"""
import uvicorn
import argparse
import threading
import time
import webbrowser
from urllib.request import urlopen
from app.api.web import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open", action="store_true", help="Open the browser once the server is ready")
    args = parser.parse_args()
    if args.open:
        def open_when_ready():
            for _ in range(50):
                try:
                    with urlopen("http://127.0.0.1:8765/api/providers", timeout=1) as response:
                        if response.status == 200:
                            webbrowser.open("http://127.0.0.1:8765")
                            return
                except OSError:
                    time.sleep(0.2)
        threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run(create_app(), host="127.0.0.1", port=8765)
