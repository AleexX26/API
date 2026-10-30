"""Pruebas en un navegador real: servidor local con un catálogo pequeño y Chromium de Playwright.
Si Playwright o Chromium no están instalados, estas pruebas se saltan (el resto de tests no las necesita)."""
import json
import socket
import threading
import time
import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")

SIZES = {"movil": {"width": 375, "height": 812}, "escritorio": {"width": 1440, "height": 900}}


def _port():
    """El comparador solo acepta escrituras desde http://127.0.0.1:8765; si ese puerto está ocupado
    (el comparador abierto), se usa otro y el modo red local, que acepta el origen del propio servidor."""
    for port in (8765, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return s.getsockname()[1]


def _catalog(tmp_path):
    from app.collectors import offers as store
    from tests.test_web import make_catalog
    cat = tmp_path / "catalog.sqlite3"
    make_catalog(cat)
    db = store.connect(cat)
    base = {"currency": "EUR", "tax": "net", "shipping": "included", "scope": "t"}
    for provider, slug, title, size, paper in (
        ("onlineprinters", "tarjetas-visita", "Tarjetas de visita", "85 x 55 mm", "350 g/m² papel estucado"),
        ("onlineprinters", "flyers-a5", "Flyers A5", "A5", "135 g/m² papel estucado"),
        ("printai", "tarjetas-85x55", "Tarjetas de visita 85x55", "85 x 55 mm", "300 g/m² papel estucado"),
    ):
        store.replace_offers(db, provider, f"https://example.test/{provider}/{slug}", title,
                             [{**base, "quantity": 500, "kind": "total", "price": "30.00"}, {**base, "quantity": 1000, "kind": "total", "price": "45.00"}],
                             "2026-10-27", [{"group": "Formato", "label": size}, {"group": "Papel", "label": paper}])
    db.close()
    return cat


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    import uvicorn
    from app.api.web import create_app
    tmp = tmp_path_factory.mktemp("browser")
    seed = tmp / "links.json"
    seed.write_text(json.dumps({"providers": {}}))
    port = _port()
    app = create_app(tmp / "work.sqlite3", seed, _catalog(tmp), lan=port != 8765)
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(5)


@pytest.fixture(scope="session")
def browser():
    with playwright_sync.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as error:  # Chromium no descargado en este PC
            pytest.skip(f"Chromium de Playwright no disponible: {error}")
        yield b
        b.close()


@pytest.fixture(params=[(s, c) for s in SIZES for c in ("light", "dark")], ids=lambda p: f"{p[0]}-{p[1]}")
def page(request, browser, server):
    size, scheme = request.param
    context = browser.new_context(viewport=SIZES[size], color_scheme=scheme)
    page = context.new_page()
    page.errors = []
    page.on("console", lambda m: m.type == "error" and page.errors.append(m.text))
    page.on("response", lambda r: r.status >= 400 and page.errors.append(f"{r.status} {r.request.method} {r.url}"))
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.base = server
    page.size = size
    yield page
    context.close()
