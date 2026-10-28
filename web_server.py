"""Run the private workspace: python web_server.py  (add --lan to share it read-only with the private network)"""
import socket
import uvicorn
import argparse
import threading
import time
import webbrowser
from urllib.request import urlopen
from app.api.web import create_app


def lan_addresses() -> list[str]:
    """Private IPv4 addresses of this PC, the ones colleagues type in their browser."""
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if info[4][0].startswith(("10.", "192.168.", "172.")):
                found.add(info[4][0])
    except OSError:
        pass
    return sorted(found)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open", action="store_true", help="Open the browser once the server is ready")
    parser.add_argument("--lan", action="store_true", help="Also serve the other computers of the private network (read-only)")
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
    if args.lan:
        print("\nEnlace para los companeros (misma red):")
        for address in lan_addresses() or ["(no se encontro la IP: ejecuta ipconfig)"]:
            print(f"   http://{address}:8765")
        print("Solo lectura para ellos. Tu PC debe seguir encendido y esta ventana abierta.\n")
    uvicorn.run(create_app(lan=args.lan), host="0.0.0.0" if args.lan else "127.0.0.1", port=8765)
