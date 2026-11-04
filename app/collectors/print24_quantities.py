"""Print24: the price of more quantities of the DEFAULT configuration of a product page.

A Print24 page embeds the prices of only five quantities (for business cards 100 to 200). When a person picks another quantity in
the "Cantidad" list, the page asks its price-matrix route (robots.txt: `Allow: */api/*`) with its own session and token. This
collector does what that person does: it opens the page in a plain Chromium (no stealth, no fingerprint tricks), declines the
cookies, picks the next missing quantity in the list and reads the answer the page itself receives. Asking the route directly
(without the page's token) gets an empty answer, so that is not done.

Same rules as the other collectors: robots.txt, 5 s between steps, stop on a challenge, and stop when the page's own first
request (the canary) is not answered. The prices go to the SAME configuration as the page's default one, so the catalog just
shows more quantities. Needs Playwright and Chromium (requirements-test.txt).
"""
import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from app.collectors.discovery import allowed
from app.collectors.sitemaps import DEFAULT_ROBOTS
from app.collectors.variants import API, CHALLENGE, PAUSE, build_payload
from app.parsers.price_matrix import MatrixError, parse_matrix
from app.parsers.product_page import calculation_data, default_configuration
from app.services.importer import canonical_context, connect, import_matrix

ROOT = Path(__file__).resolve().parents[2]
CARDS = "https://print24.com/es/productos-impresion/tarjetas-de-visita"
QUANTITY_BOX = re.compile(r"^\s*[\d.]+ Unidades?\s*$")


def quantity_options(data: dict) -> list[int]:
    """Every quantity the product offers, ascending."""
    found = set()
    for box in data["itemMaster"]["boxes"]:
        if box["propGroupName"] == "quantity":
            for prop in box["properties"]:
                digits = "".join(c for c in " ".join(part for part in prop["propertyTranslated"] if part) if c.isdigit())
                if digits:
                    found.add(int(digits))
    return sorted(found)


def missing_quantities(data: dict, have: set[int], maximum: int) -> list[int]:
    """The quantities from the one the page starts on up to `maximum` that have no price stored yet."""
    start = min(have) if have else 0
    return [q for q in quantity_options(data) if start <= q <= maximum and q not in have]


def stored_quantities(db: sqlite3.Connection, configuration_id: str) -> set[int]:
    return {row[0] for row in db.execute("SELECT DISTINCT q.value FROM prices p JOIN quantities q ON q.id=p.quantity_id WHERE p.configuration_id=?", (configuration_id,))}


def same_properties(sent: dict, data: dict) -> bool:
    """The request the page sent is for the page's default configuration (only the quantity differs)."""
    ids = lambda properties: sorted((p["name"], str(p["id"])) for p in properties)
    return ids(sent.get("properties", [])) == ids(build_payload(data)["properties"])


def is_matrix_request(response) -> bool:
    return response.request.method == "POST" and response.url.endswith("/itemmaster/calculation/price-matrix")


def collect(db_path: Path, urls: list[str], *, maximum: int = 1000, headless: bool = True, log=print) -> dict:
    from playwright.sync_api import TimeoutError as PageTimeout
    from playwright.sync_api import sync_playwright

    robots = DEFAULT_ROBOTS.read_text(encoding="utf-8-sig")
    if not allowed(robots, API):
        raise ValueError("robots.txt does not permit the price-matrix route")
    db = connect(db_path)
    now = datetime.now(timezone.utc)
    summary = {"pages": 0, "steps": 0, "stored_quantities": 0, "unavailable": 0, "pages_without_list": 0}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            page = browser.new_page(locale="es-ES", viewport={"width": 1300, "height": 1000})
            for number, url in enumerate(urls):
                if number:
                    time.sleep(PAUSE)
                first = []
                watch = lambda r: first.append(r) if is_matrix_request(r) else None
                page.on("response", watch)
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(4000)
                html = page.content()
                page.remove_listener("response", watch)
                if any(m in html.lower() for m in CHALLENGE):
                    raise ValueError(f"Possible access challenge at {url}; stop for manual review")
                data = calculation_data(html)
                _, context = default_configuration(html, url=url, observed_at=now)
                cid = hashlib.sha256(canonical_context(context).encode()).hexdigest()
                if not db.execute("SELECT 1 FROM configurations WHERE id=?", (cid,)).fetchone():
                    log(json.dumps({"url": url.rsplit("/", 1)[-1], "skipped": "configuración por defecto sin recoger"}))
                    continue
                if not first or not first[0].text().strip():  # canary: the page's own first price request
                    raise ValueError(f"Canary failed at {url}: the page's own price request was not answered; stop")
                decline = page.get_by_text("Declino", exact=True)
                if decline.count():  # the most private choice of the cookie banner
                    decline.first.click()
                    page.wait_for_timeout(1500)
                summary["pages"] += 1
                answered = 0  # quantities of this page the site already answered
                try:
                    for quantity in missing_quantities(data, stored_quantities(db, cid), maximum):
                        if quantity in stored_quantities(db, cid):  # an earlier answer already carried it
                            continue
                        time.sleep(PAUSE)
                        summary["steps"] += 1
                        box = page.locator("div[class*='Selectbox'][class*='handler']").filter(has_text=QUANTITY_BOX).first
                        box.scroll_into_view_if_needed()
                        box.click()
                        with page.expect_response(is_matrix_request, timeout=30000) as asked:
                            page.get_by_role("listitem").filter(has_text=re.compile(rf"^\s*{quantity} Unidades?\s*$")).first.click()
                        reply = asked.value
                        answered += 1
                        text = reply.text()
                        try:
                            parse_matrix(text)
                        except MatrixError:
                            summary["unavailable"] += 1
                            continue
                        if not same_properties(json.loads(reply.request.post_data or "{}"), data):
                            summary["unavailable"] += 1
                            continue
                        before = len(stored_quantities(db, cid))
                        import_matrix(db, text, context, source=f"{url}#quantity={quantity}")
                        summary["stored_quantities"] += len(stored_quantities(db, cid)) - before
                except PageTimeout:
                    if answered:  # the site answered before and now does not: stop, do not keep asking
                        raise ValueError(f"Print24 stopped answering at {url} after {answered} quantities; stop for manual review")
                    # nothing was ever answered: this page has no quantity list like the others (custom sizes...)
                    summary["pages_without_list"] += 1
                log(json.dumps({"url": url.rsplit("/", 1)[-1], **summary}))
        finally:
            browser.close()
            db.close()
    return summary


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", type=Path, default=ROOT / "data/catalog.sqlite3")
    cli.add_argument("--max", type=int, default=1000, help="highest quantity to collect")
    cli.add_argument("--visible", action="store_true", help="show the browser window")
    cli.add_argument("--todas", action="store_true", help="every Print24 page already collected (about 1-2 h), not only the business cards")
    cli.add_argument("url", nargs="*", default=[CARDS])
    args = cli.parse_args()
    urls = args.url
    if args.todas:
        with sqlite3.connect(args.db) as conn:
            urls = [r[0] for r in conn.execute("SELECT url FROM product_pages WHERE status='ok' ORDER BY url")]
    print(json.dumps(collect(args.db, urls, maximum=args.max, headless=not args.visible), indent=1))
