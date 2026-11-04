"""Print24: the exact price of a business card for every combination of print sides, paper and finishing.

A Print24 product page is a configurator: each choice (sides, paper, finishing, quantity...) is a list, and when something is
chosen the page asks its own price-matrix route and draws the answer. This collector does what a person does, in a plain
Chromium (no stealth, no copied sessions or tokens): it opens the page, declines the cookies, picks each option in the page's own
lists, 5 seconds apart, and reads the price-matrix answer the page itself receives (robots.txt: `Allow: */api/*`).

Choosing one option can change another (a paper that does not take a finishing, for instance), so the configuration stored with a
price is the one the page SHOWS when the answer arrives, not the one that was intended. Same rules as the other collectors:
robots.txt first, 5 s between steps, stop on a challenge or when the page's first answer (canary) is not a price matrix.
Prices are net of VAT, the total includes the shipping of each delivery option. Needs Playwright and Chromium (requirements-test.txt).
"""
import itertools
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from app.collectors import offers, sitemaps
from app.collectors.discovery import allowed
from app.collectors.laimprentadeinternet import slug
from app.collectors.sitemaps import DEFAULT_ROBOTS
from app.collectors.variants import API, CHALLENGE, PAUSE
from app.parsers.price_matrix import MatrixError, parse_matrix

ROOT = Path(__file__).resolve().parents[2]
PROVIDER = "print24"
CARDS = "https://print24.com/es/productos-impresion/tarjetas-de-visita"
HANDLER = "div[class*='Selectbox'][class*='handler']"
MAX_CONFIGS = 150
SCOPE = "configuración elegida en el configurador de Print24; precio sin IVA; el total incluye el envío de cada plazo"
DELIVERY = {"standard": "Estándar", "express": "Exprés", "priority": "Prioritario"}
# What each list of the configurator is, from the text it shows
KINDS = {
    "sides": re.compile(r"^\d+ caras?$"),
    "format": re.compile(r"^Formato "),
    "orientation": re.compile(r"^(Horizontal|Vertical)$"),
    "paper": re.compile(r"g/m²"),
    "inks": re.compile(r"tintas"),
    "finishing": re.compile(r"^(Sin Acabados|Barniz|Relieve|Plastificado|Laminado)"),
    "proof": re.compile(r"prueba"),
    "quantity": re.compile(r"^\d[\d.]* Unidades?$"),
}
SIDES_WANTED = ("1 cara", "2 caras")
FINISHING_WANTED = ("Sin Acabados", "Barniz protector", "Plastificado", "Laminado en caliente")


def box_index(texts: list[str], kind: str) -> int | None:
    """Position of the list of this kind among the lists the page shows."""
    return next((i for i, text in enumerate(texts) if KINDS[kind].search(text)), None)


def read_state(texts: list[str]) -> dict:
    """What the configurator shows: one text per list of interest (finishing keeps the lists that appear after it)."""
    def text(kind):
        i = box_index(texts, kind)
        return texts[i] if i is not None else ""
    start, end = box_index(texts, "finishing"), box_index(texts, "proof")
    finishing = " · ".join(texts[start:end]) if start is not None and end is not None and end > start else text("finishing")
    return {"sides": text("sides"), "format": text("format").removeprefix("Formato ").strip(), "orientation": text("orientation"),
            "paper": text("paper"), "inks": text("inks"), "finishing": finishing}


def describe(state: dict, delivery: str) -> tuple[str, list[dict]]:
    """Name suffix and spec groups of one displayed configuration x delivery type."""
    finishing = state["finishing"]
    finish_label = "sin acabado" if finishing.lower().startswith("sin acabado") else finishing
    spec = [{"group": "Formato", "label": state["format"]}, {"group": "Orientación", "label": state["orientation"]},
            {"group": "Papel", "label": state["paper"]}, {"group": "Impresión", "label": " · ".join(x for x in (state["sides"], state["inks"]) if x)},
            {"group": "Acabados", "label": finish_label}]
    name = " · ".join(x for x in (state["sides"], state["paper"], finish_label, DELIVERY.get(delivery, delivery)) if x)
    return name, [s for s in spec if s["label"]]


def build_products(url: str, title: str, state: dict, prices: list) -> list[dict]:
    """One product per delivery type of the configuration, with a row per quantity (cheapest total of each)."""
    by_delivery: dict[str, dict[int, tuple]] = {}
    for price in prices:
        slot = by_delivery.setdefault(price.delivery_type, {})
        if price.quantity_value not in slot or price.total_net < slot[price.quantity_value][0]:
            slot[price.quantity_value] = (price.total_net, int(price.delivery_days) if str(price.delivery_days).isdigit() else None)
    products = []
    for delivery in sorted(by_delivery, key=lambda d: list(DELIVERY).index(d) if d in DELIVERY else 9):
        name, spec = describe(state, delivery)
        rows = [{"quantity": q, "kind": "total", "price": total, "currency": "EUR", "tax": "net", "shipping": "included", "scope": SCOPE,
                 "delivery_days": days} for q, (total, days) in sorted(by_delivery[delivery].items())]
        spec = spec + [{"group": "Plazo de producción", "label": f"{rows[0]['delivery_days']} días hábiles"}] if rows and rows[0]["delivery_days"] else spec
        products.append({"url": f"{url}#{slug(name)}", "name": f"{title} · {name}", "rows": rows, "spec": spec})
    return products


def with_current(options: list[str], current: str, wanted: tuple = ()) -> list[str]:
    """The options of a list plus the one the page already shows (it is missing from the list it opens), first; only those wanted."""
    pool = ([current] if current else []) + [o for o in options if o != current]
    return [o for o in pool if not wanted or o.startswith(wanted)]


def configurations(sides: list[str], papers: list[str], finishes: list[str], limit: int = MAX_CONFIGS) -> tuple[list[tuple], bool]:
    """Every combination to try, papers outermost (changing the paper is what the page answers slowest), cut at `limit`."""
    combos = [(s, p, f) for p in papers for s in sides for f in finishes]
    return combos[:limit], len(combos) > limit


def is_matrix(response) -> bool:
    return response.request.method == "POST" and response.url.endswith("/itemmaster/calculation/price-matrix")


def collect(db_path: Path, url: str = CARDS, *, max_configs: int = MAX_CONFIGS, maximum: int = 1000, headless: bool = True,
            now: datetime | None = None, log=print) -> dict:
    from playwright.sync_api import TimeoutError as PageTimeout
    from playwright.sync_api import sync_playwright

    now = now or datetime.now(timezone.utc)
    robots = DEFAULT_ROBOTS.read_text(encoding="utf-8-sig")
    if not allowed(robots, API):
        raise ValueError("robots.txt does not permit the price-matrix route")
    db = offers.connect(db_path)
    summary = {"steps": 0, "configurations": 0, "products": 0, "prices": 0, "skipped": 0, "cut": False}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            try:
                page = browser.new_page(locale="es-ES", viewport={"width": 1300, "height": 1000})
                answers = []
                page.on("response", lambda r: answers.append(r) if is_matrix(r) else None)
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                if any(m in page.content()[:6000].lower() for m in CHALLENGE):
                    raise ValueError(f"Possible access challenge at {url}; stop for manual review")
                if not answers or not answers[0].text().strip():
                    raise ValueError(f"Canary failed at {url}: the page's own price request was not answered; stop")
                decline = page.get_by_text("Declino", exact=True)
                if decline.count():
                    decline.first.click()
                    page.wait_for_timeout(1500)
                title = (page.locator("h1").first.inner_text() if page.locator("h1").count() else "Tarjetas de visita").strip()[:60] or "Tarjetas de visita"

                def texts() -> list[str]:
                    return page.locator(HANDLER).evaluate_all("els => els.map(e => e.innerText.replace(/\\s+/g, ' ').trim())")

                def listed() -> set[str]:
                    return {t.strip() for t in page.get_by_role("listitem").all_inner_texts()}

                def open_list(kind: str) -> list[str]:
                    """Open the list of this kind and return its options (those that were not on the page before)."""
                    index = box_index(texts(), kind)
                    if index is None:
                        return []
                    before = listed()
                    time.sleep(PAUSE)
                    box = page.locator(HANDLER).nth(index)
                    box.scroll_into_view_if_needed()
                    box.dispatch_event("click")
                    page.wait_for_timeout(700)
                    return [t.replace("\n", " ").strip() for t in page.get_by_role("listitem").all_inner_texts() if t.strip() and t not in before]

                def choose(kind: str, wanted: str) -> bool:
                    """Pick `wanted` in the list of this kind; True when the page answered with a new price matrix."""
                    options = open_list(kind)
                    if not any(o.startswith(wanted) for o in options):
                        page.keyboard.press("Escape")
                        return False
                    item = page.get_by_role("listitem").filter(has_text=re.compile(rf"^\s*{re.escape(wanted)}")).filter(visible=True).first
                    summary["steps"] += 1
                    try:
                        with page.expect_response(is_matrix, timeout=20000):
                            item.dispatch_event("click")
                    except PageTimeout:
                        return False
                    page.wait_for_timeout(1500)
                    return True

                first_state = read_state(texts())  # the option the page shows is not in its own list: add it
                papers = with_current([o for o in open_list("paper") if KINDS["paper"].search(o)], first_state["paper"])
                page.keyboard.press("Escape")
                sides = with_current([o for o in open_list("sides") if o in SIDES_WANTED], first_state["sides"], SIDES_WANTED)
                page.keyboard.press("Escape")
                finishes = with_current([o for o in open_list("finishing") if o.startswith(FINISHING_WANTED)], first_state["finishing"].split(" · ")[0], FINISHING_WANTED)
                page.keyboard.press("Escape")
                combos, summary["cut"] = configurations(sides, papers, finishes, max_configs)
                seen = set()
                for side, paper, finish in combos:
                    state = read_state(texts())
                    for kind, wanted in (("paper", paper), ("sides", side), ("finishing", finish)):
                        if not state[kind].startswith(wanted):
                            if not choose(kind, wanted):
                                summary["skipped"] += 1
                                break
                            state = read_state(texts())
                    else:
                        if (state["sides"], state["paper"], state["finishing"]) in seen:
                            continue  # the page ended up in a configuration already read
                        seen.add((state["sides"], state["paper"], state["finishing"]))
                        matrix = []
                        try:
                            matrix = parse_matrix(answers[-1].text())
                        except MatrixError:
                            summary["skipped"] += 1
                            continue
                        have = {p.quantity_value for p in matrix}
                        for quantity in [o for o in open_list("quantity") if KINDS["quantity"].search(o)]:
                            number = int("".join(c for c in quantity.split()[0] if c.isdigit()))
                            if number in have or number > maximum:
                                continue
                            if not choose("quantity", quantity.split()[0]):
                                continue
                            try:
                                more = parse_matrix(answers[-1].text())
                            except MatrixError:
                                continue
                            matrix += more
                            have |= {p.quantity_value for p in more}
                        matrix = [p for p in matrix if p.quantity_value <= maximum]
                        state = read_state(texts())
                        for product in build_products(url, title, state, matrix):
                            offers.replace_offers(db, PROVIDER, product["url"], product["name"], product["rows"], now.isoformat(), product["spec"])
                            summary["products"] += 1
                            summary["prices"] += len(product["rows"])
                        summary["configurations"] += 1
                        log(json.dumps({"config": [state["sides"], state["paper"], state["finishing"]], "quantities": sorted(have), **summary}, ensure_ascii=False))
            finally:
                browser.close()
    finally:
        db.close()
    return summary


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", type=Path, default=ROOT / "data/catalog.sqlite3")
    cli.add_argument("--max-configs", type=int, default=MAX_CONFIGS, help="combinaciones máximas")
    cli.add_argument("--max", type=int, default=1000, help="cantidad máxima")
    cli.add_argument("--visible", action="store_true", help="show the browser window")
    cli.add_argument("url", nargs="?", default=CARDS)
    args = cli.parse_args()
    print(json.dumps(collect(args.db, args.url, max_configs=args.max_configs, maximum=args.max, headless=not args.visible), indent=1, ensure_ascii=False))
