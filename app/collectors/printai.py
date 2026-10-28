"""Printai: net total of the default configuration, from the product page itself.

Same rules as the other collectors (robots.txt first, 5 s between requests, no redirects, no cookies, cache).
Each page carries the price of ONE selection (its default quantity). The price calculator for other
quantities lives behind routes that Printai's robots.txt forbids (price_calculate.php and friends), so they are
never called: one product gives one price point. Net, VAT and gross are read from the page and cross-checked.
"""
import html as htmllib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.collectors import crawl, offers, sitemaps
from app.collectors.index_homepages import navigation_allowed
from app.parsers.price_matrix import MatrixError

ROOT = Path(__file__).resolve().parents[2]
ROBOTS = ROOT / "data/homepage-index/printai.robots.txt"
CHALLENGE = ("cf-chl-", "verify you are human", "just a moment", "access denied", "attention required")
SELECT = re.compile(r"<select([^>]*)>(.*?)</select>", re.S)
ATTR = {key: re.compile(r"(?<![\w-])" + key + r'\s*=\s*"([^"]+)"') for key in ("name", "id")}
SELECTED = re.compile(r'<option[^>]*selected[^>]*>(.*?)</option>', re.S)


def plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def hidden(page: str, name: str) -> Decimal:
    match = re.search(rf'name="{re.escape(name)}"[^>]*value="([\d.]+)"|id="{re.escape(name)}"[^>]*value="([\d.]+)"', page)
    if not match:
        raise MatrixError(f"Hidden field {name} not found")
    return Decimal(match.group(1) or match.group(2))


def product_ld(page: str) -> dict:
    for raw in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in (data if isinstance(data, list) else data.get("@graph", [data])):
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    raise MatrixError("No Product data in page")


def parse_page(page: str) -> dict:
    ld = product_ld(page)
    offer = ld.get("offers") or {}
    if offer.get("priceCurrency") != "EUR":
        raise MatrixError("Unexpected currency")
    net = hidden(page, "hidden_total_price")
    tax = hidden(page, "taxAmt[]")
    gross = hidden(page, "total_price_with_tax")
    if abs(net + tax - gross) > Decimal("0.01"):
        raise MatrixError(f"net {net} + VAT {tax} differs from gross {gross}")
    if Decimal(str(offer.get("price"))) != gross:
        raise MatrixError(f"ld+json price {offer.get('price')} differs from page gross {gross}")
    labels = dict(re.findall(r'<label[^>]*for="([^"]+)"[^>]*>(.*?)</label>', page, re.S))
    quantity, spec = None, []
    for attrs, body in SELECT.findall(page):
        name, ident = (ATTR[k].search(attrs) for k in ("name", "id"))
        name, ident = name.group(1) if name else "", ident.group(1) if ident else ""
        selected = SELECTED.search(body) or re.search(r"<option[^>]*>(.*?)</option>", body, re.S)  # browsers pick the first option
        if not selected:
            continue
        text = plain(selected.group(1))
        if name == "prdqty":
            quantity = int(re.sub(r"\D", "", text))
        elif name.startswith("aoptions[") or name == "prdsize":
            label = plain(re.sub(r'<div class="d-none.*?</div></div>', "", labels.get(ident, ""), flags=re.S)) or "Tamaño"
            if (label, text) not in [(s["group"], s["label"]) for s in spec]:
                spec.append({"group": label, "label": text})
    if not quantity:
        raise MatrixError("Selected quantity not found")
    return {"name": ld["name"], "quantity": quantity, "net": net, "gross": gross, "spec": spec}


LANGUAGES = {"fr", "pt", "en", "de", "it", "ca", "eu", "gl", "nl"}


def sitemap_urls(path: Path) -> list[str]:
    """Spanish product-looking pages of the cached sitemap.xml (no language prefix, no listing pages)."""
    out = set()
    for loc in re.findall(r"<loc>(.*?)</loc>", path.read_text(encoding="utf-8")):
        url = loc.strip()
        segments = [x for x in url.split("printai.es/", 1)[-1].split("/") if x]
        if len(segments) == 1 and segments[0] not in LANGUAGES and not url.endswith(("/categories/", "/products/")):
            out.add(url if url.endswith("/") else url + "/")
    return sorted(out)


def collect(db_path: Path, urls: list[str], cache_dir: Path, robots_file: Path = ROBOTS,
            now: datetime | None = None, log=None) -> dict:
    now = now or datetime.now(timezone.utc)
    robots = robots_file.read_text(encoding="utf-8-sig")
    blocked = [u for u in urls if not navigation_allowed(robots, u)]
    if blocked:
        raise ValueError(f"robots.txt does not permit: {blocked[:3]}")
    db = offers.connect(db_path)
    state, report = {}, []
    guard = crawl.Guard(now, state)
    try:
        for url in urls:
            cache_file = cache_dir / (url.rstrip("/").rsplit("/", 1)[1] + ".html")
            try:
                raw, cached = guard.fetch(url, cache_file)
            except crawl.Gone as gone:
                entry = {"url": url, "from_cache": False, "status": "failed", "name": None, "tiers": 0, "error": str(gone)}
                offers.record_page(db, "printai", url, now.isoformat(), "failed", 0, entry["error"])
                report.append(entry)
                if log:
                    log(len(report), len(urls), entry)
                continue
            page = raw.decode("utf-8")
            if any(m in page.lower() for m in CHALLENGE):
                raise ValueError(f"Possible access challenge at {url}; stop for manual review")
            fetched = json.loads(cache_file.with_suffix(".json").read_text(encoding="utf-8"))["fetched_at"]
            entry = {"url": url, "from_cache": cached, "status": "ok", "name": None, "tiers": 0, "error": None}
            try:
                parsed = parse_page(page)
                entry.update(name=parsed["name"], tiers=1)
                offers.replace_offers(db, "printai", url, parsed["name"], [
                    {"quantity": parsed["quantity"], "kind": "total", "price": parsed["net"], "currency": "EUR",
                     "tax": "net", "shipping": "included",
                     "scope": "selección por defecto, entrega incluida según la web (un solo punto de precio)"}],
                    fetched, parsed["spec"])
            except (MatrixError, ValueError) as exc:
                entry.update(status="failed", error=str(exc)[:300])
            offers.record_page(db, "printai", url, fetched, entry["status"], entry["tiers"], entry["error"])
            report.append(entry)
            if log:
                log(len(report), len(urls), entry)
    finally:
        db.close()
    return {"network_requests": state.get("requests", 0), "pages": report}


if __name__ == "__main__":
    import argparse
    import sys
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", type=Path, default=ROOT / "data/catalog.sqlite3")
    cli.add_argument("--cache", type=Path, default=ROOT / "data/cache/printai")
    cli.add_argument("--sitemap", action="store_true", help="collect everything listed in the cached sitemap")
    cli.add_argument("--limit", type=int)
    cli.add_argument("url", nargs="*")
    args = cli.parse_args()
    chosen = args.url or sitemap_urls(args.cache / "sitemap.xml")
    if args.limit:
        chosen = chosen[:args.limit]

    def progress(done, total, entry):
        print(json.dumps({"n": done, "of": total, "status": entry["status"], "tiers": entry["tiers"], "cached": entry["from_cache"],
                          "url": entry["url"].rstrip("/").rsplit("/", 1)[-1], "error": entry["error"]}, ensure_ascii=False),
              file=sys.stderr, flush=True)

    report = collect(args.db, chosen, args.cache, log=progress)
    print(json.dumps({"network_requests": report["network_requests"], "pages": len(report["pages"]),
                      "ok": sum(p["status"] == "ok" for p in report["pages"]),
                      "failed": sum(p["status"] != "ok" for p in report["pages"])}, indent=1))
