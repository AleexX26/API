"""La Imprenta de Internet (our own shop): the price of every configuration of its business cards.

The shop is WooCommerce with the Uni CPO configurator. The price of a configuration comes from the shop's own price
calculator (admin-ajax action `uni_cpo_price_calc`, which its robots.txt allows). The page loads its scripts only once a
visitor scrolls, so a real browser opens the page, scrolls like a visitor and changes the page's own selects, one change
every 5 seconds; every answer of the calculator is stored with the combination it belongs to. Prices are net (the page
says "impuestos no incluidos"); shipping to the peninsula is free, the express option already includes its surcharge.

Needs Playwright and its Chromium (`requirements-test.txt`). Cached answers are reused for 30 days, so a rerun asks nothing.
"""
import json
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs

from app.collectors import offers, sitemaps
from app.collectors.index_homepages import navigation_allowed

ROOT = Path(__file__).resolve().parents[2]
PROVIDER = "laimprentadeinternet"
SITE = "https://laimprentadeinternet.com"
PAGES = [f"{SITE}/impresion-de-tarjetas-de-visita/", f"{SITE}/tarjetas-de-visita-barniz-uvi-madrid/"]
AJAX = f"{SITE}/wp-admin/admin-ajax.php"
PAUSE = 5
CACHE_DAYS = 30
SCOPE = "configuración elegida en el configurador de la propia web; precio sin IVA, envío a la península incluido"


def slug(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def parse_form(page: str) -> list[dict]:
    """The configurator's selects: [{name, options: [{value, label}]}] without the 'Por favor, selecciona' placeholder."""
    page = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    form = []
    for name, body in re.findall(r'<select\b[^>]*name="(uni_cpo_[^"]+)"[^>]*>(.*?)</select>', page, re.S):
        options = [{"value": v, "label": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", label)).strip()}
                   for v, label in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>', body, re.S) if v]
        if options:
            form.append({"name": name, "options": options})
    return form


def describe(page: str) -> dict:
    """Name, product id and the product's description (it states format, paper weight and paper) from the page."""
    info = {"name": "Tarjetas de visita", "description": "", "product_id": ""}
    for raw in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else data.get("@graph", [data]):
            if isinstance(item, dict) and item.get("@type") == "Product":
                info["name"] = item.get("name") or info["name"]
                info["description"] = item.get("description", "")
    if match := re.search(r'name="cpo_product_id"[^>]*value="(\d+)"', page) or re.search(r'value="(\d+)"[^>]*name="cpo_product_id"', page):
        info["product_id"] = match.group(1)
    return info


def fixed(name: str) -> bool:
    """The design service is not a characteristic of the card: always the first (free) option."""
    return "diseno" in name


def combinations(form: list[dict]) -> list[dict]:
    """Every combination in snake order: each step changes exactly one select, so each change asks one new price."""
    dims = [[(f["name"], o["value"]) for o in (f["options"][:1] if fixed(f["name"]) else f["options"])] for f in form]

    def snake(level: int) -> list[dict]:
        if level == len(dims):
            return [{}]
        inner, out = snake(level + 1), []
        for index, (name, value) in enumerate(dims[level]):
            out += [{name: value, **combo} for combo in (inner if index % 2 == 0 else inner[::-1])]
        return out

    return snake(0)


def key_of(combo: dict) -> str:
    return "|".join(f"{k}={combo[k]}" for k in sorted(combo))


def days_in(label: str) -> tuple[int | None, str]:
    match = re.search(r"(\d+)\s*(?:-\s*(\d+))?\s*d[ií]as", label)
    if not match:
        return None, ""
    low, high = int(match.group(1)), int(match.group(2) or match.group(1))
    return high, f"{low}-{high} días hábiles" if high != low else f"{low} días hábiles"


def spec_for(info: dict, form: list[dict], combo: dict) -> tuple[list[dict], int | None, list[str]]:
    """Characteristics as the other providers' pages name them (so the card filters read them the same), the delivery
    days and the pieces of the configuration's name."""
    from app.services.cards import grams_in, sizes_in
    text = info["description"]
    spec, days, names = [], None, []
    if sizes := sorted(sizes_in(text), key=lambda s: -s[0]):
        spec.append({"group": "Formato", "label": f"{sizes[0][0]} x {sizes[0][1]} mm"})
    if grams := sorted(grams_in(text)):
        spec.append({"group": "Papel", "label": f"{grams[0]} g/m² papel estucado" if "estucado" in text.lower() else f"{grams[0]} g/m²"})
    for field in form:
        label = next(o["label"] for o in field["options"] if o["value"] == combo[field["name"]])
        name = field["name"]
        if "unidades" in name:
            continue
        if "caras" in name:
            spec.append({"group": "Impresión", "label": "4+0 una cara" if label.startswith("1") else "4+4 dos caras"})
            names.append(label)
        elif "acabado" in name:
            spec.append({"group": "Acabados", "label": "sin acabado" if label.lower().startswith("sin") else label})
            names.append("Sin acabado" if label.lower().startswith("sin") else label)
        elif "envio" in name:
            days, shown = days_in(label)
            spec.append({"group": "Plazo de producción", "label": shown or label})
            names.append(re.sub(r"\s*[+]\s*\d+\s*€", "", label).replace("gratis", "").strip())
        elif fixed(name):
            spec.append({"group": "Revisión de tu diseño", "label": "revisión gratis"})
    return spec, days, names


def build_offers(url: str, info: dict, form: list[dict], prices: dict) -> list[dict]:
    """One catalog product per (sides, finish, delivery) with a tier for every quantity: [{url, name, rows, spec}]."""
    quantity_field = next(f for f in form if "unidades" in f["name"])
    others = [f for f in form if f is not quantity_field]
    products = []
    for rest in combinations(others):
        rows, spec, names = [], [], []
        for option in sorted(quantity_field["options"], key=lambda o: int(re.sub(r"\D", "", o["label"]))):
            combo = {**rest, quantity_field["name"]: option["value"]}
            if key_of(combo) not in prices:
                continue
            spec, days, names = spec_for(info, form, combo)
            rows.append({"quantity": int(re.sub(r"\D", "", option["label"])), "kind": "total", "price": Decimal(str(prices[key_of(combo)]["net"])),
                         "currency": "EUR", "tax": "net", "shipping": "included", "scope": SCOPE, "delivery_days": days})
        if rows:
            label = " · ".join(names)
            products.append({"url": f"{url}#{slug(label)}", "name": f"{info['name']} · {label}" if label else info["name"], "rows": rows, "spec": spec})
    return products


def is_calc(response) -> bool:
    post = response.request.post_data or ""
    return "admin-ajax" in response.url and "uni_cpo_price_calc" in post


def state_of(response) -> dict:
    data = parse_qs(response.request.post_data or "")
    return {k[5:-1]: v[0] for k, v in data.items() if k.startswith("data[uni_cpo_")}


def read_prices(url: str, form: list[dict], prices: dict, log=None) -> None:
    """Drive the page's selects in a real browser and store the calculator's answer for every missing combination."""
    from playwright.sync_api import sync_playwright
    wanted = [c for c in combinations(form) if key_of(c) not in prices]
    if not wanted:
        return
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1300, "height": 1100})
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            page.mouse.move(400, 500)
            page.mouse.wheel(0, 600)
            page.wait_for_timeout(1500)
            page.mouse.wheel(0, 400)
            page.wait_for_timeout(4000)
            current = {f["name"]: page.eval_on_selector(f"select[name={f['name']}]", "e=>e.value") for f in form}

            def record(response):
                body = response.json()
                if not body.get("success") or body["data"].get("errors"):
                    raise ValueError(f"The calculator answered with an error: {str(body)[:200]}")
                variables = body["data"]["price_vars"]
                prices[key_of(state_of(response))] = {"net": variables["raw_price"], "gross": variables["raw_price_tax_rev"]}

            def change(name: str, value: str):
                current[name] = value
                state = dict(current)
                with page.expect_response(lambda r: is_calc(r) and state_of(r) == state, timeout=30000) as info:
                    page.select_option(f"select[name={name}]", value)
                record(info.value)
                time.sleep(PAUSE)

            for combo in wanted:
                for name, value in combo.items():
                    if current[name] != value:
                        change(name, value)
                if key_of(combo) not in prices:  # the page was already in this state: leave it and come back
                    name = next(iter(combo))
                    other = next(o["value"] for f in form if f["name"] == name for o in f["options"] if o["value"] != combo[name])
                    change(name, other)
                    change(name, combo[name])
                if log:
                    log(len(prices), len(combinations(form)))
        finally:
            browser.close()


SITEMAP = f"{SITE}/product-sitemap.xml"
LINK_NOTE = "ficha propia sin precio recogido"


def sitemap_pages(db_path: Path, cache_dir: Path, now: datetime | None = None) -> dict:
    """Every product page of our shop (its product sitemap), so that a search always shows at least our web.

    The pages that already have prices in the comparator are left out; the others are stored as links without price
    (`supplier_pages` failed with LINK_NOTE), which the screens list as "Ver en nuestra web".
    """
    now = now or datetime.now(timezone.utc)
    cache_dir.mkdir(parents=True, exist_ok=True)
    state: dict = {}
    robots, _ = sitemaps.fetch_cached(f"{SITE}/robots.txt", cache_dir / "robots.txt", now, state, expected="text")
    if not navigation_allowed(robots.decode("utf-8", "replace"), SITEMAP):
        raise ValueError("robots.txt does not permit the product sitemap")
    xml, _ = sitemaps.fetch_cached(SITEMAP, cache_dir / "product-sitemap.xml", now, state, expected="text")
    pages = [u for u in re.findall(r"<loc>([^<]+)</loc>", xml.decode("utf-8", "replace")) if u.startswith(SITE + "/")]
    db = offers.connect(db_path)
    linked = priced = 0
    try:
        with db:
            db.execute("DELETE FROM supplier_pages WHERE provider=? AND error=?", (PROVIDER, LINK_NOTE))
        for url in pages:
            if db.execute("SELECT 1 FROM supplier_offers WHERE provider=? AND (product_url=? OR product_url LIKE ?) LIMIT 1", (PROVIDER, url, url + "#%")).fetchone():
                priced += 1
                continue
            offers.record_page(db, PROVIDER, url, now.isoformat(), "failed", 0, LINK_NOTE)
            linked += 1
    finally:
        db.close()
    return {"pages": len(pages), "with_prices": priced, "links": linked}


def collect(db_path: Path, cache_dir: Path, urls: list[str] | None = None, now: datetime | None = None, log=None) -> dict:
    now = now or datetime.now(timezone.utc)
    cache_dir.mkdir(parents=True, exist_ok=True)
    state: dict = {}
    robots, _ = sitemaps.fetch_cached(f"{SITE}/robots.txt", cache_dir / "robots.txt", now, state, expected="text")
    robots = robots.decode("utf-8", "replace")
    db = offers.connect(db_path)
    report = []
    try:
        for url in urls or PAGES:
            if not navigation_allowed(robots, url) or not navigation_allowed(robots, AJAX):
                raise ValueError(f"robots.txt does not permit {url} or the price calculator")
            if db.execute("SELECT 1 FROM supplier_offers WHERE provider=? AND product_url LIKE ? LIMIT 1", (PROVIDER, f"{url}#tarifa-%")).fetchone():
                report.append({"url": url, "status": "skipped", "reason": "esta página usa la tarifa propia importada del Excel"})
                continue  # decided before asking the shop for anything
            raw, _ = sitemaps.fetch_cached(url, cache_dir / f"{slug(url.rstrip('/').rsplit('/', 1)[-1])}.html", now, state, expected="text/html")
            page = raw.decode("utf-8", "replace")
            if re.search(r"captcha|verify you are human|access denied|just a moment", page[:5000], re.I):
                raise ValueError(f"Possible access challenge at {url}; stop for manual review")
            form, info = parse_form(page), describe(page)
            if not any("unidades" in f["name"] for f in form):
                offers.record_page(db, PROVIDER, url, now.isoformat(), "failed", 0, "configurator not found")
                report.append({"url": url, "status": "failed", "products": 0})
                continue
            store = cache_dir / f"{slug(url.rstrip('/').rsplit('/', 1)[-1])}-prices.json"
            saved = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
            fresh = saved.get("fetched_at") and now - datetime.fromisoformat(saved["fetched_at"]) < timedelta(days=CACHE_DAYS)
            prices = saved.get("prices", {}) if fresh and saved.get("form") == form else {}
            started = saved.get("fetched_at") if prices else now.isoformat()
            try:
                read_prices(url, form, prices, log)
            finally:  # keep what was read even if the run stops half way
                store.write_text(json.dumps({"fetched_at": started, "form": form, "prices": prices}, ensure_ascii=False), encoding="utf-8")
            products = build_offers(url, info, form, prices)
            for product in products:
                offers.replace_offers(db, PROVIDER, product["url"], product["name"], product["rows"], started, product["spec"])
            offers.record_page(db, PROVIDER, url, started, "ok", len(prices), None)
            report.append({"url": url, "status": "ok", "products": len(products), "prices": len(prices)})
    finally:
        db.close()
    return {"pages": report}


if __name__ == "__main__":
    import argparse
    import sys
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", type=Path, default=ROOT / "data/catalog.sqlite3")
    cli.add_argument("--cache", type=Path, default=ROOT / "data/cache/laimprentadeinternet")
    cli.add_argument("--sitemap", action="store_true", help="solo guardar las fichas de nuestra tienda (sitemap) como enlaces sin precio")
    cli.add_argument("url", nargs="*")
    args = cli.parse_args()
    if args.sitemap:
        print(json.dumps(sitemap_pages(args.db, args.cache), ensure_ascii=False, indent=1))
        raise SystemExit(0)
    result = collect(args.db, args.cache, args.url or None,
                     log=lambda done, total: print(json.dumps({"precios": done, "de": total}), file=sys.stderr, flush=True))
    print(json.dumps(result, ensure_ascii=False, indent=1))
