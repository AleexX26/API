"""Print24: prices of ONE-OPTION-AT-A-TIME variations of each product's default configuration.

Run it with the browser environment (.venv-browser): a plain Chromium (no stealth, no fingerprint spoofing) loads the
product page like a person would, and the page's own session sends each price-matrix request from inside the page.
Same rules as the other collectors: robots.txt, 5 s between requests, resumable cache, stop on a challenge.

NOT YET RUN AGAINST THE LIVE SITE. Safety nets, because a plain HTTP client received empty answers earlier:
the unchanged default selection is requested first as a canary. If the canary comes back empty, the run stops
(that would mean the site is not answering us). If only a variation is empty, that combination is simply invalid.
"""
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.collectors.discovery import allowed
from app.collectors.sitemaps import DEFAULT_ROBOTS
from app.parsers.price_matrix import MatrixError, parse_matrix
from app.parsers.product_page import SPANNED, calculation_data
from app.services.importer import connect, import_matrix

ROOT = Path(__file__).resolve().parents[2]
API = "https://print24.com/api/es/itemmaster/calculation/price-matrix"
PAUSE = 5
SKIP_GROUPS = SPANNED | {"proofpages", "availability", "quality", "paper_core", "finishing_size", "individualization_desc"}
CHALLENGE = ("cf-chl-", "verify you are human", "just a moment", "access denied", "attention required")
MAX_CONSECUTIVE_EMPTY = 5

SCHEMA = "CREATE TABLE IF NOT EXISTS config_specs (configuration_id TEXT PRIMARY KEY, title TEXT NOT NULL, spec_json TEXT NOT NULL);"

FETCH_JS = """async (payload) => {
  const r = await fetch('/api/es/itemmaster/calculation/price-matrix', {method: 'POST',
    headers: {'Content-Type': 'application/json', 'Accept': 'application/json'}, body: JSON.stringify(payload)});
  return {status: r.status, text: await r.text()};
}"""


def variations(data: dict) -> list[dict]:
    """Every alternative option of every visible group, one change at a time."""
    master = data["itemMaster"]
    selected = {p["name"]: str(p["id"]) for p in master["selectedProps"]}
    found = []
    for box in master["boxes"]:
        name = box["propGroupName"]
        if box.get("hide") or name in SKIP_GROUPS or name not in selected:
            continue
        for prop in box["properties"]:
            option = str(prop["pgrId"])
            label = " ".join(part.strip() for part in prop["propertyTranslated"] if part and part.strip())
            if option == selected[name] or not label or label.lower().startswith("elija"):
                continue
            found.append({"group": name, "title": (box.get("boxTitleTranslated") or name).strip(), "option_id": option, "label": label})
    return found


def base_properties(data: dict) -> list[dict]:
    return [{"id": str(p["id"]), "name": p["name"]} for p in data["itemMaster"]["selectedProps"] if p["name"] not in SPANNED]


def build_payload(data: dict, change: dict | None = None) -> dict:
    """The request the page itself sends, with at most one option replaced."""
    properties = base_properties(data)
    if change:
        properties = [{"id": change["option_id"] if p["name"] == change["group"] else p["id"], "name": p["name"]} for p in properties]
    link = data["itemMaster"]["deepLink"]
    values = dict(part.split("=", 1) for part in link.split("&"))
    return {"delivery_country_code": values["delivery_country_code"], "product_alias_id": int(values["product_alias_id"]),
            "properties": properties, "quantities": [row["quantity"]["id"] for row in data["priceMatrix"]], "premium_file_check": 0}


def variant_spec(data: dict, change: dict) -> list[dict]:
    from app.collectors.specs import default_spec
    altered = json.loads(json.dumps(data))
    for prop in altered["itemMaster"]["selectedProps"]:
        if prop["name"] == change["group"]:
            prop["id"] = change["option_id"]
    return default_spec(altered)


def store_variant(db: sqlite3.Connection, product_url: str, data: dict, change: dict, text: str, now: datetime) -> str:
    """Import one variation through the normal importer (atomic, with history) and keep its readable spec."""
    properties = base_properties(data)
    properties = [{"id": change["option_id"] if p["name"] == change["group"] else p["id"], "name": p["name"]} for p in properties]
    parse_matrix(text)  # raises MatrixError on anything that is not a valid matrix
    currency = json.loads(text)[0]["quantity"]["shipping_type"][0]["price"]["currency"]
    link = dict(part.split("=", 1) for part in data["itemMaster"]["deepLink"].split("&"))
    context = {"product_id": link["product_alias_id"], "properties": properties, "country": link["delivery_country_code"],
               "currency": currency, "account_scope": "public-web-no-session", "services": {},
               "validity_evidence": f"Variation '{change['title']}: {change['label']}' of the default configuration, read from {product_url}",
               "observed_at": now.isoformat(), "valid_until": (now + timedelta(days=31)).isoformat()}
    cid = import_matrix(db, text, context, source=f"{product_url}#{change['group']}={change['option_id']}")
    with db:
        db.execute("INSERT OR REPLACE INTO config_specs VALUES (?,?,?)",
                   (cid, f"{change['title']}: {change['label']}", json.dumps(variant_spec(data, change), ensure_ascii=False)))
    return cid


def collect(db_path: Path, urls: list[str], cache_dir: Path, *, max_variations: int | None = None, headless: bool = True,
            log=print) -> dict:
    from playwright.sync_api import sync_playwright  # only in the browser environment

    robots = DEFAULT_ROBOTS.read_text(encoding="utf-8-sig")
    if not allowed(robots, API):
        raise ValueError("robots.txt does not permit the price-matrix route")
    db = connect(db_path)
    db.executescript(SCHEMA)
    summary = {"products": 0, "stored": 0, "invalid": 0, "cached": 0}
    now = datetime.now(timezone.utc)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            page = browser.new_page(locale="es-ES")
            first = True
            for url in urls:
                if not first:
                    time.sleep(PAUSE)
                first = False
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                html = page.content()
                if any(m in html.lower() for m in CHALLENGE):
                    raise ValueError(f"Possible access challenge at {url}; stop for manual review")
                data = calculation_data(html)

                def ask(change):
                    time.sleep(PAUSE)
                    reply = page.evaluate(FETCH_JS, build_payload(data, change))
                    return reply["status"], reply["text"]

                status, text = ask(None)  # canary: the unchanged default selection
                if status != 200 or not text.strip():
                    raise ValueError(f"Canary failed at {url} (status {status}, empty={not text.strip()}): the site is not answering; stop")
                summary["products"] += 1
                empties = 0
                todo = variations(data)[: max_variations or None]
                for change in todo:
                    cache = cache_dir / f"{data['itemMaster']['deepLink'].split('product_alias_id=')[1]}_{change['group']}_{change['option_id']}.json"
                    if cache.exists():
                        summary["cached"] += 1
                        continue
                    status, text = ask(change)
                    try:
                        parse_matrix(text)
                    except MatrixError:
                        summary["invalid"] += 1
                        empties += 1
                        if empties >= MAX_CONSECUTIVE_EMPTY:  # re-check the canary: invalid combinations vs a site that stopped answering
                            status, text = ask(None)
                            if status != 200 or not text.strip():
                                raise ValueError(f"{empties} empty answers and the canary now fails at {url}; stop for manual review")
                            empties = 0
                        continue
                    empties = 0
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_text(text, encoding="utf-8")
                    store_variant(db, url, data, change, text, now)
                    summary["stored"] += 1
                log(json.dumps({"url": url.rsplit("/", 1)[-1], **summary}))
        finally:
            browser.close()
            db.close()
    return summary


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", type=Path, default=ROOT / "data/catalog.sqlite3")
    cli.add_argument("--cache", type=Path, default=ROOT / "data/cache/variants")
    cli.add_argument("--max-variations", type=int, help="limit variations per product")
    cli.add_argument("--visible", action="store_true", help="show the browser window")
    cli.add_argument("url", nargs="+")
    args = cli.parse_args()
    print(json.dumps(collect(args.db, args.url, args.cache, max_variations=args.max_variations, headless=not args.visible), indent=1))
