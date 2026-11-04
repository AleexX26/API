"""Truyol: the price of every quantity and delivery time of a product page, read the way a person reads it.

Truyol's robots.txt only forbids /files/ and PDFs. A product page shows a price table (rows = quantities, columns =
delivery times) and its own script asks `formulario/precio` when something is chosen. This collector opens the page in a
plain Chromium (no stealth), picks each quantity (and each print-sides / lamination choice) in the page's own lists,
5 seconds apart, and reads the prices the page itself draws. Prices are net of VAT (the page says "excl. IVA"), shipping
to the peninsula is free ("Envío Gratis"). Each configuration x delivery time becomes one product in `supplier_offers`.

Same rules as the other collectors: robots.txt first, 5 s between steps, no login, stop on a challenge or when the
page's own first price request is not answered (canary). Needs Playwright and Chromium (requirements-test.txt).
"""
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.collectors import offers, sitemaps
from app.collectors.index_homepages import navigation_allowed
from app.collectors.laimprentadeinternet import slug

ROOT = Path(__file__).resolve().parents[2]
PROVIDER = "truyol"
SITE = "https://truyol.com"
CARDS = f"{SITE}/es/material-publicitario/tarjetas-de-visita-clasicas"
PRICE_ROUTE = "formulario/precio"
PAUSE = 5
SCOPE = "tabla de precios de la ficha de Truyol; precio sin IVA, envío gratis a la península"
CHALLENGE = ("captcha", "verify you are human", "access denied", "just a moment")
DELIVERY = {"3H": ("Recogida en tienda", 1), "24H": ("24 horas", 1), "2-3D": ("2 a 3 días", 3), "4-5D": ("4 a 5 días", 5), "6-7D": ("6 a 7 días", 7)}
SIDES = {"1C": "4+0 una cara", "2C": "4+4 dos caras"}


def price_rows(buttons: list[dict]) -> tuple[dict, int]:
    """{(delivery code, quantity): net price} from the price buttons of the table, and how many were inconsistent.

    A button whose gross price does not match net + VAT is dropped: it is not a price this collector can trust.
    """
    found, bad = {}, 0
    for b in buttons:
        try:
            net, gross, vat = Decimal(b["precio"]), Decimal(b["precio_con_iva"]), Decimal(b["iva"])
            quantity = int(b["cnt"])
        except (KeyError, ValueError, InvalidOperation):
            bad += 1
            continue
        if not (net.is_finite() and net > 0) or abs(net * (1 + vat / 100) - gross) > Decimal("0.03"):
            bad += 1
            continue
        found.setdefault((b.get("plazo", ""), quantity), net.quantize(Decimal("0.01")))
    return found, bad


def paper_label(text: str) -> str:
    """'Estucado Mate 350 g/m2' -> '350 g/m² papel estucado mate' (the wording the other providers' pages use)."""
    grams = re.search(r"(\d{2,4})\s*g", text)
    kind = re.sub(r"\d{2,4}\s*g(?:/m[2²])?", "", text).strip().lower()
    return " ".join(x for x in (f"{grams.group(1)} g/m²" if grams else "", "papel " + kind if kind else "") if x)


def format_label(text: str) -> str:
    """'8,5x5,5cm' -> '85 x 55 mm' (millimetres, like the other providers' pages)."""
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(cm|mm)?\s*", text)
    if not m:
        return text.strip()
    scale = 10 if (m.group(3) or "mm") == "cm" else 1
    number = lambda raw: Decimal(raw.replace(",", ".")) * scale
    return f"{number(m.group(1)).normalize():f} x {number(m.group(2)).normalize():f} mm"


def describe(selected: dict, plazo: str) -> tuple[str, list[dict]]:
    """The product name suffix and the spec groups of one configuration x delivery time."""
    sides = SIDES.get(selected.get("sides", ""), selected.get("sides_text", ""))
    lamination = selected.get("lamination_text", "")
    finish = "sin acabado" if not lamination or lamination.lower() in ("no", "sin") else "plastificado " + lamination.lower()
    spec = [{"group": "Formato", "label": format_label(selected.get("format", ""))},
            {"group": "Papel", "label": paper_label(selected.get("paper", ""))},
            {"group": "Impresión", "label": sides},
            {"group": "Acabados", "label": finish},
            {"group": "Plazo de producción", "label": f"{DELIVERY[plazo][0]} hábiles" if plazo in DELIVERY else plazo}]
    name = " · ".join(x for x in (sides, finish.capitalize(), DELIVERY.get(plazo, (plazo,))[0]) if x)
    return name, [s for s in spec if s["label"]]


def build_products(url: str, title: str, selected: dict, prices: dict) -> list[dict]:
    """One product per delivery time of this configuration, with a row per quantity."""
    products = []
    for plazo in sorted({p for p, _ in prices}, key=lambda p: DELIVERY.get(p, ("", 99))[1]):
        name, spec = describe(selected, plazo)
        rows = [{"quantity": q, "kind": "total", "price": price, "currency": "EUR", "tax": "net", "shipping": "included", "scope": SCOPE,
                 "delivery_days": DELIVERY.get(plazo, ("", None))[1]} for (p, q), price in sorted(prices.items(), key=lambda kv: kv[0][1]) if p == plazo]
        if rows:
            products.append({"url": f"{url}#{slug(name)}", "name": f"{title} · {name}", "rows": rows, "spec": spec})
    return products


READ_BUTTONS = """() => [...document.querySelectorAll('#tabla-precios button.precio_btn')].filter(b => b.offsetParent !== null).map(b => ({
  plazo: b.dataset.plazo, precio: b.dataset.precio, precio_con_iva: b.dataset.precio_con_iva, iva: b.dataset.iva, cnt: b.dataset.cnt}))"""
READ_SELECTED = """() => { const text = id => { const s = document.getElementById(id); return s && s.selectedIndex >= 0 ? s.options[s.selectedIndex].textContent.trim() : ''; };
  const value = id => { const s = document.getElementById(id); return s ? s.value : ''; };
  return {format: text('e_frmt_abierto'), paper: text('e_soporte'), sides: value('e_imp_caras'), sides_text: text('e_imp_caras'),
          lamination: value('e_plast_tipo'), lamination_text: value('e_plast_tipo') === 'NO' ? 'No' : text('e_plast_tipo')}; }"""
OPTIONS = """id => { const s = document.getElementById(id); return s ? [...s.options].map(o => o.value) : []; }"""


def collect(db_path: Path, cache_dir: Path, urls: list[str] | None = None, *, headless: bool = True, now: datetime | None = None, log=print) -> dict:
    from playwright.sync_api import sync_playwright

    now = now or datetime.now(timezone.utc)
    cache_dir.mkdir(parents=True, exist_ok=True)
    robots, _ = sitemaps.fetch_cached(f"{SITE}/robots.txt", cache_dir / "robots.txt", now, {}, expected="text")
    robots = robots.decode("utf-8", "replace")
    urls = urls or [CARDS]
    blocked = [u for u in urls if not navigation_allowed(robots, u)]
    if blocked:
        raise ValueError(f"robots.txt does not permit: {blocked[:3]}")
    db = offers.connect(db_path)
    summary = {"pages": 0, "steps": 0, "products": 0, "prices": 0, "inconsistent": 0}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            try:
                page = browser.new_page(locale="es-ES", viewport={"width": 1300, "height": 1000})
                for number, url in enumerate(urls):
                    if number:
                        time.sleep(PAUSE)
                    first = []
                    page.on("response", lambda r: first.append(r) if r.request.method == "POST" and PRICE_ROUTE in r.url else None)
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(5000)
                    if any(m in page.content()[:6000].lower() for m in CHALLENGE):
                        raise ValueError(f"Possible access challenge at {url}; stop for manual review")
                    if not first or first[0].status != 200 or '"estado":"OK"' not in first[0].text():  # canary
                        raise ValueError(f"Canary failed at {url}: the page's own price request was not answered; stop")
                    title = page.evaluate("() => (document.querySelector('h1') || document.body).textContent.trim().replace(/\\s+/g, ' ')")[:80] or "Truyol"
                    sides_values = page.evaluate(OPTIONS, "e_imp_caras") or [""]
                    lamination_values = page.evaluate(OPTIONS, "e_plast_tipo") or [""]
                    stored, found_any = 0, False
                    for sides in sides_values:
                        for lamination in lamination_values:
                            for field, value in (("e_imp_caras", sides), ("e_plast_tipo", lamination)):
                                if value and page.evaluate("id => document.getElementById(id).value", field) != value:
                                    time.sleep(PAUSE)
                                    summary["steps"] += 1
                                    with page.expect_response(lambda r: r.request.method == "POST" and PRICE_ROUTE in r.url, timeout=30000):
                                        page.select_option(f"#{field}", value)
                                    page.wait_for_timeout(1500)
                            prices, bad = price_rows(page.evaluate(READ_BUTTONS))
                            summary["inconsistent"] += bad
                            for quantity in page.evaluate(OPTIONS, "e_copias"):
                                if any(q == int(quantity) for _, q in prices):
                                    continue
                                time.sleep(PAUSE)
                                summary["steps"] += 1
                                with page.expect_response(lambda r: r.request.method == "POST" and PRICE_ROUTE in r.url, timeout=30000):
                                    page.select_option("#e_copias", quantity)
                                page.wait_for_timeout(1500)
                                more, bad = price_rows(page.evaluate(READ_BUTTONS))
                                summary["inconsistent"] += bad
                                for key, price in more.items():
                                    prices.setdefault(key, price)
                            selected = page.evaluate(READ_SELECTED)
                            for product in build_products(url, title, selected, prices):
                                offers.replace_offers(db, PROVIDER, product["url"], product["name"], product["rows"], now.isoformat(), product["spec"])
                                summary["products"] += 1
                                summary["prices"] += len(product["rows"])
                                stored += len(product["rows"])
                                found_any = True
                            log(json.dumps({"config": f"{sides}/{lamination}", "prices": len(prices), **summary}))
                    offers.record_page(db, PROVIDER, url, now.isoformat(), "ok" if found_any else "failed", stored, None if found_any else "no prices read")
                    summary["pages"] += 1
            finally:
                browser.close()
    finally:
        db.close()
    return summary


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", type=Path, default=ROOT / "data/catalog.sqlite3")
    cli.add_argument("--visible", action="store_true", help="show the browser window")
    cli.add_argument("url", nargs="*", default=[CARDS])
    args = cli.parse_args()
    print(json.dumps(collect(args.db, ROOT / "data/cache/truyol", args.url, headless=not args.visible), indent=1, ensure_ascii=False))
