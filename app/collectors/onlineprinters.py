"""Onlineprinters: net total price per quantity, from the server-rendered product page (/p/...).

Same rules as the other collectors: robots.txt first (its agent-specific rules are honoured; the ajax and
productConfiguration JSON routes they forbid are never touched), 5 s between network requests, no redirects,
no cookies, pages cached. The quantity tiles show the net price of the whole order, with standard shipping
free according to the page. The default configuration's labels (format, paper...) are stored with each page.
"""
import html as htmllib
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.collectors import crawl, offers, sitemaps
from app.collectors.index_homepages import navigation_allowed
from app.parsers.price_matrix import MatrixError

ROOT = Path(__file__).resolve().parents[2]
ROBOTS = ROOT / "data/homepage-index/onlineprinters.robots.txt"
CHALLENGE = ("cf-chl-", "verify you are human", "just a moment", "access denied", "attention required")
MONEY = re.compile(r"^(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})$")
TILE = re.compile(r'<label class="([^"]*)"[^>]*>(?:(?!</label>).)*?opidProductConfigTileLabel1">\s*(\d{1,3}(?:\.\d{3})*|\d+)\s*'
                  r'</div>(?:(?!</label>).)*?&euro;\s*([\d.]+,\d{2})', re.S)
HEAD = re.compile(r'<dt[^>]*productConfigItemHeadTitle[^>]*>(.*?)</dt><dd[^>]*>(.*?)</dd>', re.S)
BASE = re.compile(r"Precio base \(sin IVA\).*?&euro;\s*(?:<[^>]+>|\s)*([\d.]+,\d{2})", re.S)
GROSS = re.compile(r"incl\. (\d+)% IVA\s*(?:<[^>]+>|\s)*&euro;\s*(?:<[^>]+>|\s)*([\d.]+,\d{2})", re.S)


def money(text: str) -> Decimal:
    match = MONEY.match(text.strip())
    if not match:
        raise MatrixError(f"Unrecognised amount {text!r}")
    return Decimal(match.group(1).replace(".", "") + "." + match.group(2))


def plain(fragment: str) -> str:
    fragment = re.sub(r"<script.*?</script>", " ", fragment, flags=re.S)
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_page(page: str) -> dict:
    """{name, tiers: [(quantity, net_total)], spec: [{group,label}]} verified against the page's own base price and VAT."""
    title = re.search(r"<title[^>]*>(.*?)</title>", page, re.S)
    if not title:
        raise MatrixError("No title")
    name = plain(title.group(1)).rsplit("|", 1)[0].strip()
    tiers, active = {}, None
    for cls, qty, price in TILE.findall(page):
        quantity, value = int(qty.replace(".", "")), money(price)
        if quantity in tiers and tiers[quantity] != value:
            raise MatrixError(f"Conflicting prices for quantity {quantity}")
        tiers[quantity] = value
        if "active" in cls.split():
            active = (quantity, value)
    if not tiers:
        raise MatrixError("No quantity/price tiles found")
    base = BASE.search(page)
    if not base or active is None or money(base.group(1)) != active[1]:
        raise MatrixError("Active quantity price does not match the page's base price")
    gross = GROSS.search(page)
    if gross:
        rate = Decimal(gross.group(1)) / 100
        if abs(active[1] * (1 + rate) - money(gross.group(2))) > Decimal("0.01"):
            raise MatrixError("Gross price inconsistent with net and VAT")
    spec = []
    for raw_title, raw_value in HEAD.findall(page):
        label = plain(raw_value)
        label = re.sub(r"productPageObj\.\S+.*$", "", label).strip()
        if label and plain(raw_title).replace("'>", "").strip() != "Cantidad":
            spec.append({"group": plain(raw_title).replace("'>", "").strip(), "label": label})
    return {"name": name, "tiers": sorted(tiers.items()), "spec": spec, "default_quantity": active[0]}


def sitemap_urls(path: Path) -> list[str]:
    """Product URLs (/p/...) from the cached products_sitemap.xml."""
    found = [u.strip() for u in re.findall(r"<loc>(.*?)</loc>", path.read_text(encoding="utf-8"))]
    return sorted({u for u in found if u.startswith("https://www.onlineprinters.es/p/")})


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
                offers.record_page(db, "onlineprinters", url, now.isoformat(), "failed", 0, entry["error"])
                report.append(entry)
                if log:
                    log(len(report), len(urls), entry)
                continue
            page = raw.decode("iso-8859-1")
            if any(m in page.lower() for m in CHALLENGE):
                raise ValueError(f"Possible access challenge at {url}; stop for manual review")
            fetched = json.loads(cache_file.with_suffix(".json").read_text(encoding="utf-8"))["fetched_at"]
            entry = {"url": url, "from_cache": cached, "status": "ok", "name": None, "tiers": 0, "error": None}
            try:
                parsed = parse_page(page)
                entry.update(name=parsed["name"], tiers=len(parsed["tiers"]))
                offers.replace_offers(db, "onlineprinters", url, parsed["name"], [
                    {"quantity": q, "kind": "total", "price": price, "currency": "EUR", "tax": "net", "shipping": "included",
                     "scope": "configuración por defecto, envío estándar gratuito según la web"}
                    for q, price in parsed["tiers"]], fetched, parsed["spec"])
            except (MatrixError, ValueError) as exc:
                entry.update(status="failed", error=str(exc)[:300])
            offers.record_page(db, "onlineprinters", url, fetched, entry["status"], entry["tiers"], entry["error"])
            report.append(entry)
            if log:
                log(len(report), len(urls), entry)
    finally:
        db.close()
    return {"network_requests": state.get("requests", 0), "pages": report}


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", type=Path, default=ROOT / "data/catalog.sqlite3")
    cli.add_argument("--cache", type=Path, default=ROOT / "data/cache/onlineprinters")
    cli.add_argument("--sitemap", type=Path, help="collect every /p/ URL of this cached products_sitemap.xml")
    cli.add_argument("--limit", type=int)
    cli.add_argument("url", nargs="*")
    args = cli.parse_args()
    chosen = args.url or sitemap_urls(args.sitemap or args.cache / "products_sitemap.xml")
    if args.limit:
        chosen = chosen[:args.limit]

    def progress(done, total, entry):
        print(json.dumps({"n": done, "of": total, "status": entry["status"], "tiers": entry["tiers"],
                          "cached": entry["from_cache"], "url": entry["url"].rsplit("/", 1)[-1], "error": entry["error"]},
                         ensure_ascii=False), file=sys.stderr, flush=True)

    report = collect(args.db, chosen, args.cache, log=progress)
    print(json.dumps({"network_requests": report["network_requests"], "pages": len(report["pages"]),
                      "ok": sum(p["status"] == "ok" for p in report["pages"]),
                      "failed": [{"url": p["url"], "error": p["error"]} for p in report["pages"] if p["status"] != "ok"]},
                     ensure_ascii=False, indent=1))
