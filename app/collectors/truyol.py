"""Truyol: the price of every quantity and delivery time of a product page, read the way a person reads it.

Truyol's robots.txt only forbids /files/ and PDFs. A product page shows a price table (rows = quantities, columns =
delivery times) and its own script asks `formulario/precio` when something is chosen. This collector opens the page in a
plain Chromium (no stealth), picks each format, paper, print-sides, lamination and quantity in the page's own lists,
5 seconds apart, and reads the prices the page itself draws. Prices are net of VAT (the page says "excl. IVA"), shipping
to the peninsula is free ("Envío Gratis"). Each configuration x delivery time becomes one product in `supplier_offers`.

Same rules as the other collectors: robots.txt first, 5 s between steps, no login, stop on a challenge or when the
page's own price request is refused (canary). A page with no price table (quote only) is noted and skipped.
Needs Playwright and Chromium (requirements-test.txt).
"""
import itertools
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
BASE = f"{SITE}/es/material-publicitario"
# The business-card family (from the links of {BASE}/tarjetas-de-visita) and the flyers page.
GROUPS = {
    "tarjetas": [f"{BASE}/{x}" for x in ("tarjetas-de-visita-clasicas", "tarjetas-de-visita-personalizadas", "tarjetas-de-visita-barnizadas",
                                          "tarjetas-de-visita-estampadas", "tarjetas-y-tarjetones-multicapa", "tarjetas-de-visita-troqueladas",
                                          "tarjetas-de-visita-con-tinta-metalizada", "tarjetas-de-visita-con-textura", "tarjetas-pvc-basica",
                                          "tarjetas-rfid")],
    "flyers": [f"{BASE}/flyers"],
}
CARDS = GROUPS["tarjetas"][0]
PRICE_ROUTE = "formulario/precio"
PAUSE = 5
MAX_CONFIGS = 120  # configurations per page; a page with more is cut and the summary says so
SCOPE = "tabla de precios de la ficha de Truyol (con el descuento que muestre la ficha); precio sin IVA, envío gratis a la península"
CHALLENGE = ("captcha", "verify you are human", "access denied", "just a moment")
DELIVERY = {"3H": ("Recogida en tienda", 1), "24H": ("24 horas", 1), "2-3D": ("2 a 3 días", 3), "4-5D": ("4 a 5 días", 5), "6-7D": ("6 a 7 días", 7)}
SIDES = {"1C": "4+0 una cara", "2C": "4+4 dos caras"}
# What a person can change on the page, in the order it is changed: (key, select id)
DIMENSIONS = (("format", "e_frmt_abierto"), ("paper", "e_soporte"), ("sides", "e_imp_caras"), ("lamination", "e_plast_tipo"))


def price_rows(buttons: list[dict]) -> tuple[dict, int]:
    """{(delivery code, quantity): net price} from the price buttons of the table, and how many were inconsistent.

    Some pages show a discount (the struck-through price is the list price): the price a customer pays is the list
    price minus `dto` percent, at most `dto_max` euros. A button whose gross price does not match that net + VAT is
    dropped: it is not a price this collector can trust.
    """
    found, bad = {}, 0
    for b in buttons:
        try:
            net, gross, vat = Decimal(b["precio"]), Decimal(b["precio_con_iva"]), Decimal(b["iva"])
            quantity = int(b["cnt"])
            percent, cap = Decimal(b.get("dto") or 0), Decimal(b.get("dto_max") or 0)
            if percent > 0:
                discount = net * percent / 100
                net -= min(discount, cap) if cap > 0 else discount
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
    """'8,5x5,5cm' -> '85 x 55 mm'; 'A5 Vertical (14,8x21cm)' -> 'A5 (148 x 210 mm)' (millimetres, like the other providers)."""
    dims = re.search(r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(cm|mm)?", text)
    if not dims:
        return text.strip()
    scale = 10 if (dims.group(3) or "mm") == "cm" else 1
    number = lambda raw: Decimal(raw.replace(",", ".")) * scale
    size = f"{number(dims.group(1)).normalize():f} x {number(dims.group(2)).normalize():f} mm"
    name = re.match(r"\s*(A\d|DL)\b", text)
    return f"{name.group(1)} ({size})" if name else size


def describe(selected: dict, plazo: str, varied: tuple = ()) -> tuple[str, list[dict]]:
    """The product name suffix and the spec groups of one configuration x delivery time.

    `varied` names the dimensions the page offers more than one value of ("format", "paper"): they go in the name so
    two configurations of the same page never share an address.
    """
    sides = SIDES.get(selected.get("sides", ""), selected.get("sides_text", ""))
    lamination = selected.get("lamination_text", "")
    finish = "sin acabado" if not lamination or lamination.lower() in ("no", "sin") else "plastificado " + lamination.lower()
    format_text, paper = format_label(selected.get("format", "")), paper_label(selected.get("paper", ""))
    spec = [{"group": "Formato", "label": format_text},
            {"group": "Papel", "label": paper},
            {"group": "Impresión", "label": sides},
            {"group": "Acabados", "label": finish},
            {"group": "Plazo de producción", "label": f"{DELIVERY[plazo][0]} hábiles" if plazo in DELIVERY else plazo}]
    parts = [format_text if "format" in varied else "", paper if "paper" in varied else "", sides, finish.capitalize(), DELIVERY.get(plazo, (plazo,))[0]]
    return " · ".join(x for x in parts if x), [s for s in spec if s["label"]]


def build_products(url: str, title: str, selected: dict, prices: dict, varied: tuple = ()) -> list[dict]:
    """One product per delivery time of this configuration, with a row per quantity."""
    products = []
    for plazo in sorted({p for p, _ in prices}, key=lambda p: DELIVERY.get(p, ("", 99))[1]):
        name, spec = describe(selected, plazo, varied)
        rows = [{"quantity": q, "kind": "total", "price": price, "currency": "EUR", "tax": "net", "shipping": "included", "scope": SCOPE,
                 "delivery_days": DELIVERY.get(plazo, ("", None))[1]} for (p, q), price in sorted(prices.items(), key=lambda kv: kv[0][1]) if p == plazo]
        if rows:
            products.append({"url": f"{url}#{slug(name)}", "name": f"{title} · {name}", "rows": rows, "spec": spec})
    return products


def configurations(options: dict, limit: int = MAX_CONFIGS) -> tuple[list[dict], bool]:
    """Every combination of the values the page offers ({key: [values]} with one value or none = fixed), cut at `limit`."""
    keys = [k for k, values in options.items() if len(values) > 1]
    combos = [dict(zip(keys, c)) for c in itertools.product(*(options[k] for k in keys))] or [{}]
    return combos[:limit], len(combos) > limit


READ_BUTTONS = """() => [...document.querySelectorAll('#tabla-precios button.precio_btn')].filter(b => b.offsetParent !== null).map(b => ({
  plazo: b.dataset.plazo, precio: b.dataset.precio, precio_con_iva: b.dataset.precio_con_iva, iva: b.dataset.iva, cnt: b.dataset.cnt,
  dto: b.dataset.dto, dto_max: b.dataset.dto_max}))"""
READ_SELECTED = """() => { const text = id => { const s = document.getElementById(id); return s && s.selectedIndex >= 0 ? s.options[s.selectedIndex].textContent.trim() : ''; };
  const value = id => { const s = document.getElementById(id); return s ? s.value : ''; };
  return {format: text('e_frmt_abierto'), paper: text('e_soporte'), sides: value('e_imp_caras'), sides_text: text('e_imp_caras'),
          lamination: value('e_plast_tipo'), lamination_text: value('e_plast_tipo') === 'NO' ? 'No' : text('e_plast_tipo')}; }"""
OPTIONS = """id => { const s = document.getElementById(id); return s && s.options ? [...s.options].map(o => o.value) : []; }"""
CURRENT = """id => { const s = document.getElementById(id); return s ? s.value : ''; }"""
TITLE = "() => (document.querySelector('h1') || document.body).textContent.trim().replace(/\\s+/g, ' ')"


def is_price_request(response) -> bool:
    return response.request.method == "POST" and PRICE_ROUTE in response.url


def collect(db_path: Path, cache_dir: Path, urls: list[str] | None = None, *, headless: bool = True, now: datetime | None = None,
            max_configs: int = MAX_CONFIGS, log=print) -> dict:
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
    summary = {"pages": 0, "steps": 0, "products": 0, "prices": 0, "inconsistent": 0, "without_prices": [], "cut": []}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            try:
                page = browser.new_page(locale="es-ES", viewport={"width": 1300, "height": 1000})
                answers = []
                page.on("response", lambda r: answers.append(r) if is_price_request(r) else None)

                def choose(selector: str, value: str) -> None:
                    time.sleep(PAUSE)
                    summary["steps"] += 1
                    with page.expect_response(is_price_request, timeout=30000):
                        page.select_option(selector, value)
                    page.wait_for_timeout(1500)

                for number, url in enumerate(urls):
                    if number:
                        time.sleep(PAUSE)
                    answers.clear()
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(5000)
                    if any(m in page.content()[:6000].lower() for m in CHALLENGE):
                        raise ValueError(f"Possible access challenge at {url}; stop for manual review")
                    if answers and (answers[0].status != 200 or '"estado":"OK"' not in answers[0].text()):  # canary: refused = stop
                        raise ValueError(f"Canary failed at {url}: the page's own price request was refused; stop")
                    if not answers or not page.evaluate(READ_BUTTONS):
                        summary["without_prices"].append(url.rsplit("/", 1)[-1])
                        offers.record_page(db, PROVIDER, url, now.isoformat(), "failed", 0, "no price table (quote only)")
                        log(json.dumps({"url": url.rsplit("/", 1)[-1], "skipped": "sin tabla de precios"}))
                        continue
                    title = page.evaluate(TITLE)[:80] or "Truyol"
                    options = {key: page.evaluate(OPTIONS, field) for key, field in DIMENSIONS}
                    combos, cut = configurations(options, max_configs)
                    varied = tuple(k for k in ("format", "paper") if len(options[k]) > 1)
                    if cut:
                        summary["cut"].append(url.rsplit("/", 1)[-1])
                    stored = 0
                    for combo in combos:
                        usable = True
                        for key, field in DIMENSIONS:
                            if key not in combo:
                                continue
                            if page.evaluate(CURRENT, field) != combo[key]:
                                if combo[key] not in page.evaluate(OPTIONS, field):  # a list that depends on an earlier choice
                                    usable = False
                                    break
                                choose(f"#{field}", combo[key])
                        if not usable:
                            continue
                        prices, bad = price_rows(page.evaluate(READ_BUTTONS))
                        summary["inconsistent"] += bad
                        for quantity in page.evaluate(OPTIONS, "e_copias"):
                            if any(q == int(quantity) for _, q in prices):
                                continue
                            choose("#e_copias", quantity)
                            more, bad = price_rows(page.evaluate(READ_BUTTONS))
                            summary["inconsistent"] += bad
                            for key, price in more.items():
                                prices.setdefault(key, price)
                        for product in build_products(url, title, page.evaluate(READ_SELECTED), prices, varied):
                            offers.replace_offers(db, PROVIDER, product["url"], product["name"], product["rows"], now.isoformat(), product["spec"])
                            summary["products"] += 1
                            summary["prices"] += len(product["rows"])
                            stored += len(product["rows"])
                        log(json.dumps({"url": url.rsplit("/", 1)[-1], "config": combo, "prices": len(prices), "products": summary["products"]}, ensure_ascii=False))
                    offers.record_page(db, PROVIDER, url, now.isoformat(), "ok" if stored else "failed", stored, None if stored else "no prices read")
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
    cli.add_argument("--grupo", choices=("tarjetas", "flyers", "todos"), default="tarjetas", help="qué fichas recoger")
    cli.add_argument("--max-configs", type=int, default=MAX_CONFIGS, help="combinaciones máximas por ficha")
    cli.add_argument("--visible", action="store_true", help="show the browser window")
    cli.add_argument("url", nargs="*", help="fichas concretas (sustituyen a --grupo)")
    args = cli.parse_args()
    chosen = args.url or (GROUPS["tarjetas"] + GROUPS["flyers"] if args.grupo == "todos" else GROUPS[args.grupo])
    print(json.dumps(collect(args.db, ROOT / "data/cache/truyol", chosen, headless=not args.visible, max_configs=args.max_configs), indent=1, ensure_ascii=False))
