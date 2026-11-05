"""WooCommerce of La Imprenta de Internet (our own shop): products and categories, READ ONLY.

It uses the shop's own REST API with a read-only key made in WooCommerce > Settings > Advanced > REST API (never a cookie or a session).
The key lives in the local `.env` file (WOO_URL, WOO_KEY, WOO_SECRET), which git ignores; it is never printed, logged or stored.

Only two routes are ever asked, both with GET: `products` and `products/categories`. Orders and customers (personal data) are never
requested, although a read key could read them. Redirects are refused (the key must not travel to another address) and the address must
be HTTPS. What is stored: name, address, type, status, SKU, base price, stock, categories, texts without HTML and the main image address.
The prices of the configurators (Uni CPO) are NOT here: they are calculated when the options are chosen, and `laimprentadeinternet.py`
reads them.
"""
import base64
import html
import json
import os
import re
import sqlite3
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPSHandler, Request, build_opener

import certifi

from app.collectors import offers, pacing
from app.collectors.discovery import NoRedirect, Redirected

ROOT = Path(__file__).resolve().parents[2]
API_PATH = "/wp-json/wc/v3/"
ALLOWED = ("products", "products/categories")  # nothing else is ever requested
PER_PAGE = 100
MAX_PAGES = 50
SCHEMA = """
CREATE TABLE IF NOT EXISTS shop_products (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT, url TEXT, type TEXT, status TEXT, sku TEXT, price TEXT, regular_price TEXT,
  sale_price TEXT, on_sale INTEGER, stock_status TEXT, stock_quantity INTEGER, categories_json TEXT, short_description TEXT,
  description TEXT, image_url TEXT, modified TEXT, fetched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS shop_categories (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT, parent INTEGER, count INTEGER, fetched_at TEXT NOT NULL);
"""


class WooError(RuntimeError):
    """An error that is safe to show: it never contains the key, the secret or any header."""


def load_env(path: Path | None = None) -> dict[str, str]:
    """KEY=VALUE lines of the .env file (comments and blank lines ignored); real environment variables win."""
    path = path or ROOT / ".env"
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    for name in ("WOO_URL", "WOO_KEY", "WOO_SECRET"):
        if os.environ.get(name):
            values[name] = os.environ[name]
    return values


def credentials(env: dict[str, str]) -> tuple[str, str, str]:
    url, key, secret = (env.get(n, "").strip() for n in ("WOO_URL", "WOO_KEY", "WOO_SECRET"))
    if not key or not secret:
        raise WooError("Faltan WOO_KEY y WOO_SECRET en el archivo .env (copia .env.example como .env y escribe tus claves)")
    if "pega_aqui" in key or "pega_aqui" in secret:
        raise WooError("El .env todavía tiene las claves de ejemplo: cámbialas por las reales de WooCommerce")
    if not key.startswith("ck_") or not secret.startswith("cs_"):
        raise WooError("Las claves de WooCommerce empiezan por ck_ (cliente) y cs_ (secreto)")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise WooError("WOO_URL debe ser una dirección HTTPS, por ejemplo https://laimprentadeinternet.com")
    return f"https://{parts.netloc}", key, secret


def request(base: str, key: str, secret: str, route: str, params: dict | None = None, opener=None) -> tuple[list, dict]:
    """One GET of an allowed route. Returns (parsed JSON, response headers)."""
    if route not in ALLOWED:
        raise WooError(f"Ruta no permitida: solo se piden {', '.join(ALLOWED)}")
    url = base + API_PATH + route + ("?" + urlencode(params) if params else "")
    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    opener = opener or build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))
    try:
        with opener.open(Request(url, headers={"Authorization": f"Basic {token}", "Accept": "application/json", "User-Agent": "ComparadorImprenta/1.0"}), timeout=60) as response:
            body, headers = response.read(20_000_001), dict(response.headers.items())
    except Redirected as exc:
        raise WooError(f"La tienda redirige a otra dirección ({exc.code}); no se envía la clave. Revisa WOO_URL (https, con o sin www)") from None
    except HTTPError as exc:
        hint = {401: "las claves no son válidas", 403: "la clave no tiene permiso de lectura o un plugin de seguridad bloquea la API",
                404: "la API REST no está disponible en esa dirección"}.get(exc.code, "error del servidor")
        raise WooError(f"WooCommerce respondió {exc.code} en «{route}»: {hint}") from None
    except (URLError, TimeoutError, OSError) as exc:
        raise WooError(f"No se pudo conectar con la tienda ({type(exc).__name__})") from None
    if len(body) > 20_000_000:
        raise WooError("Respuesta demasiado grande")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise WooError("La tienda no devolvió JSON (¿una página de error o de seguridad?)") from None
    if not isinstance(data, list):
        raise WooError("Respuesta inesperada de la API (no es una lista)")
    return data, headers


def fetch_all(base: str, key: str, secret: str, route: str, opener=None, pause=pacing.human_pause, log=None) -> list[dict]:
    items: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        if page > 1:
            pause()
        data, headers = request(base, key, secret, route, {"per_page": PER_PAGE, "page": page}, opener)
        items += data
        total = int({k.lower(): v for k, v in headers.items()}.get("x-wp-totalpages", "1") or 1)
        if log:
            log(route, page, total, len(items))
        if page >= total or not data:
            break
    return items


def plain(text) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(text or "")))).strip()


def num(value) -> str | None:
    value = "" if value is None else str(value).strip()
    return value or None


def product_row(p: dict, now: str) -> tuple:
    images = p.get("images") or []
    return (int(p["id"]), plain(p.get("name")), p.get("slug") or "", p.get("permalink") or "", p.get("type") or "", p.get("status") or "",
            p.get("sku") or "", num(p.get("price")), num(p.get("regular_price")), num(p.get("sale_price")), 1 if p.get("on_sale") else 0,
            p.get("stock_status") or "", p.get("stock_quantity"),
            json.dumps([{"id": c.get("id"), "name": plain(c.get("name"))} for c in p.get("categories") or []], ensure_ascii=False),
            plain(p.get("short_description")), plain(p.get("description")), (images[0].get("src") if images else "") or "", p.get("date_modified") or "", now)


def store(db_path: Path, products: list[dict], categories: list[dict], now: datetime | None = None) -> dict:
    """Replace the stored shop data atomically: if anything fails, the previous data stays."""
    now = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    rows = [product_row(p, now) for p in products]
    cats = [(int(c["id"]), plain(c.get("name")), c.get("slug") or "", int(c.get("parent") or 0), int(c.get("count") or 0), now) for c in categories]
    db = offers.connect(db_path)
    try:
        db.executescript(SCHEMA)
        with db:
            db.execute("DELETE FROM shop_products")
            db.execute("DELETE FROM shop_categories")
            db.executemany("INSERT INTO shop_products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            db.executemany("INSERT INTO shop_categories VALUES (?,?,?,?,?,?)", cats)
    finally:
        db.close()
    return {"products": len(rows), "categories": len(cats), "fetched_at": now}


def _canonical(url: str) -> str:
    parts = urlsplit(url or "")
    return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}"


def coverage(db_path: Path) -> dict:
    """Which published products of the shop have prices in the comparator, only a link, or nothing at all."""
    db = offers.connect(db_path)
    try:
        db.executescript(SCHEMA)
        priced = {_canonical(u) for (u,) in db.execute("SELECT DISTINCT substr(product_url, 1, instr(product_url || '#', '#') - 1) FROM supplier_offers WHERE provider='laimprentadeinternet'")}
        linked = {_canonical(u) for (u,) in db.execute("SELECT url FROM supplier_pages WHERE provider='laimprentadeinternet'")}
        report = {"with_prices": [], "link_only": [], "missing": []}
        for name, url in db.execute("SELECT name, url FROM shop_products WHERE status='publish' ORDER BY name"):
            key = _canonical(url)
            report["with_prices" if key in priced else "link_only" if key in linked else "missing"].append({"name": name, "url": url})
        return report
    finally:
        db.close()


def list_products(db_path: Path, q: str = "", limit: int = 100) -> list[dict]:
    db = offers.connect(db_path)
    try:
        db.executescript(SCHEMA)
        db.row_factory = sqlite3.Row
        like = f"%{q.strip().lower()}%"
        found = db.execute("SELECT * FROM shop_products WHERE lower(name || ' ' || categories_json || ' ' || sku) LIKE ? ORDER BY name LIMIT ?", (like, limit)).fetchall()
        return [{**dict(r), "categories": json.loads(r["categories_json"])} for r in found]
    finally:
        db.close()


def run(db_path: Path, env: dict[str, str] | None = None, opener=None, pause=pacing.human_pause, log=None) -> dict:
    base, key, secret = credentials(env if env is not None else load_env())
    products = fetch_all(base, key, secret, "products", opener, pause, log)
    categories = fetch_all(base, key, secret, "products/categories", opener, pause, log)
    summary = store(db_path, products, categories)
    cover = coverage(db_path)
    return {**summary, "published": len(cover["with_prices"]) + len(cover["link_only"]) + len(cover["missing"]),
            "with_prices": len(cover["with_prices"]), "link_only": len(cover["link_only"]),
            "missing_in_comparator": [p["name"] for p in cover["missing"]], "link_only_names": [p["name"] for p in cover["link_only"]]}


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", type=Path, default=ROOT / "data/catalog.sqlite3")
    cli.add_argument("--env", type=Path, default=ROOT / ".env")
    pacing.add_arguments(cli)
    args = cli.parse_args()
    pacing.apply(args)
    try:
        print(json.dumps(run(args.db, load_env(args.env), log=lambda route, page, total, count: print(f"{route}: página {page} de {total} ({count})", file=sys.stderr, flush=True)),
                         ensure_ascii=False, indent=1))
    except WooError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
