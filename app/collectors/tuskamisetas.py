"""TusKamisetas: unit price per quantity tier ("PRECIO POR CANTIDADES") from public product pages.

Same rules as the Print24 collectors: robots.txt checked first, 5 s between network requests, no redirects,
no cookies, pages cached on disk. The table is the price of the garment WITHOUT personalisation, per unit.
The page does not say whether VAT is included, so `tax_status` is stored as 'unknown' (shipping 'excluded': it is the garment unit price). No ajax price call is made.
An HTTP-level problem or a possible challenge stops the run; an uninterpretable page is recorded and skipped.
"""
import json
import re
import sqlite3
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from pathlib import Path

from app.collectors import crawl, offers, sitemaps
from app.collectors.index_homepages import navigation_allowed
from app.parsers.price_matrix import MatrixError

ROOT = Path(__file__).resolve().parents[2]
ROBOTS = ROOT / "data/homepage-index/tuskamisetas.robots.txt"
CHALLENGE = ("cf-chl-", "verify you are human", "just a moment", "access denied", "attention required")

UNIT_PRICE = re.compile(r"^(\d{1,3}(?:\.\d{3})*|\d+),(\d{2,4})\s?€$")  # cheap items show 3 decimals


def unit_price(cell: str) -> Decimal:
    match = UNIT_PRICE.match(cell)
    if not match:
        raise MatrixError(f"Unrecognised unit price {cell!r}")
    return Decimal(match.group(1).replace(".", "") + "." + match.group(2))


QTY = re.compile(r"^\+?(\d+)\+?$")  # headers appear as "1000" or "+1000"

class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self._row, self._cell, self._in = [], None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
            self._in += 1
        elif tag == "tr" and self._in:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell).replace("\xa0", " ")).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.tables[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._in:
            self._in -= 1

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def product_ld(html: str) -> dict:
    for raw in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in (data if isinstance(data, list) else data.get("@graph", [data])):
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    raise MatrixError("No Product data in page")


def parse_page(html: str) -> dict:
    """Return {name, currency, tiers: [{group, variant, min_quantity, unit_price}]}, checked against ld+json."""
    ld = product_ld(html)
    offer = ld.get("offers") or {}
    currency = offer.get("priceCurrency")
    if not currency or len(currency) != 3:
        raise MatrixError("Currency missing")
    parser = Tables()
    parser.feed(html)
    tiers, seen, duplicates = [], {}, 0
    for table in parser.tables:
        head = table[0] if table else []
        matches = [QTY.match(c) for c in head[1:]]
        if len(head) < 2 or not all(matches) or not all(int(m.group(1)) > 0 for m in matches):
            continue  # not a quantity table (e.g. the size chart)
        quantities = [int(m.group(1)) for m in matches]
        for row in table[1:]:
            if len(row) != len(head):
                raise MatrixError(f"Row {row[:1]} does not match the quantity header")
            for qty, cell in zip(quantities, row[1:]):
                price, key = unit_price(cell), (head[0], row[0], qty)
                if key in seen:  # the page may repeat a column; only identical prices can be merged
                    if seen[key] != price:
                        raise MatrixError(f"Conflicting prices for {key}: {seen[key]} vs {price}")
                    duplicates += 1
                    continue
                seen[key] = price
                tiers.append({"group": head[0], "variant": row[0], "min_quantity": qty, "unit_price": price})
    if not tiers:
        raise MatrixError("No price-per-quantity table found")
    prices = [t["unit_price"] for t in tiers]
    low, high = offer.get("lowPrice"), offer.get("highPrice")
    cents = lambda value: value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)  # the page rounds to cents
    if low is not None and Decimal(str(low)) != cents(min(prices)):
        raise MatrixError(f"Table minimum {min(prices)} differs from page lowPrice {low}")
    if high is not None and Decimal(str(high)) != cents(max(prices)):
        raise MatrixError(f"Table maximum {max(prices)} differs from page highPrice {high}")
    return {"name": ld["name"], "currency": currency, "tiers": tiers, "duplicate_columns": duplicates}


def sitemap_urls(path: Path) -> list[str]:
    """Product URLs (/es/producto/...) from the cached sitemap-modelo.xml."""
    found = [u.strip() for u in re.findall(r"<loc>(.*?)</loc>", path.read_text(encoding="utf-8"))]
    return sorted({u for u in found if u.startswith("https://www.tuskamisetas.com/es/producto/")})


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
            cache_file = cache_dir / (url.rstrip("/").rsplit("/", 1)[1].lower() + ".html")
            try:
                raw, cached = guard.fetch(url, cache_file)
            except crawl.Gone as gone:
                entry = {"url": url, "from_cache": False, "status": "failed", "name": None, "tiers": 0, "duplicate_columns": 0, "error": str(gone)}
                offers.record_page(db, "tuskamisetas", url, now.isoformat(), "failed", 0, entry["error"])
                report.append(entry)
                if log:
                    log(len(report), len(urls), entry)
                continue
            html = raw.decode("utf-8")
            if any(m in html.lower() for m in CHALLENGE):
                raise ValueError(f"Possible access challenge at {url}; stop for manual review")
            fetched = json.loads(cache_file.with_suffix(".json").read_text(encoding="utf-8"))["fetched_at"]
            entry = {"url": url, "from_cache": cached, "status": "ok", "name": None, "tiers": 0, "duplicate_columns": 0, "error": None}
            try:
                page = parse_page(html)
                entry.update(name=page["name"], tiers=len(page["tiers"]), duplicate_columns=page["duplicate_columns"])
                offers.replace_offers(db, "tuskamisetas", url, page["name"], [
                    {"group": t["group"], "variant": t["variant"], "quantity": t["min_quantity"], "kind": "unit",
                     "price": t["unit_price"], "currency": page["currency"], "tax": "unknown", "shipping": "excluded",
                     "scope": "prenda sin personalizar, precio por unidad"} for t in page["tiers"]], fetched)
            except (MatrixError, KeyError, ValueError, sqlite3.IntegrityError) as exc:
                entry.update(status="failed", error=str(exc)[:300])
            offers.record_page(db, "tuskamisetas", url, fetched, entry["status"], entry["tiers"], entry["error"])
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
    cli.add_argument("--cache", type=Path, default=ROOT / "data/cache/tuskamisetas")
    cli.add_argument("--sitemap", action="store_true", help="collect everything listed in the cached sitemap")
    cli.add_argument("--limit", type=int)
    cli.add_argument("url", nargs="*")
    args = cli.parse_args()
    chosen = args.url or sitemap_urls(args.cache / "sitemap-modelo.xml")
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
