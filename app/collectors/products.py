"""Collect the default configuration and prices of Print24 product pages.

Reads product URLs from `catalog_urls` (see sitemaps.py), checks robots.txt, waits 5 s between
network requests, follows no redirects, keeps no cookies and caches each page on disk.
An HTTP-level problem (redirect, non-200, wrong content type, possible challenge) stops the whole
run for review. A page that downloads fine but cannot be interpreted is recorded and skipped.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.collectors import sitemaps
from app.collectors.discovery import allowed
from app.parsers.price_matrix import MatrixError
from app.parsers.product_page import default_configuration
from app.services.importer import connect, import_matrix

ROOT = Path(__file__).resolve().parents[2]
CHALLENGE = ("cf-chl-", "verify you are human", "captcha")

SCHEMA = """
CREATE TABLE IF NOT EXISTS product_pages (
  url TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('ok','failed')),
  product_id TEXT, configuration_id TEXT, prices INTEGER, error TEXT, updated_at TEXT NOT NULL);
"""


def cache_name(url: str) -> str:
    return url.split("/es/", 1)[1].strip("/").replace("/", "__") + ".html"


def product_urls(db_path: Path, limit: int | None = None) -> list[str]:
    db = sqlite3.connect(db_path)
    try:
        rows = db.execute("SELECT url FROM catalog_urls WHERE kind='product' ORDER BY url").fetchall()
    finally:
        db.close()
    urls = [r[0] for r in rows]
    return urls[:limit] if limit else urls


def collect(db_path: Path, urls: list[str], cache_dir: Path, robots_file: Path = sitemaps.DEFAULT_ROBOTS,
            now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    robots = robots_file.read_text(encoding="utf-8-sig")
    blocked = [u for u in urls if not allowed(robots, u)]
    if blocked:
        raise ValueError(f"robots.txt does not permit: {blocked[:3]}")
    db = connect(db_path)
    db.executescript(SCHEMA)
    state: dict = {}
    report = []
    try:
        for url in urls:
            cache_file = cache_dir / cache_name(url)
            raw, cached = sitemaps.fetch_cached(url, cache_file, now, state, expected="text/html")
            html = raw.decode("utf-8")
            if any(m in html.lower() for m in CHALLENGE):
                raise ValueError(f"Possible access challenge at {url}; stop for manual review")
            fetched = json.loads(cache_file.with_suffix(".json").read_text(encoding="utf-8"))["fetched_at"]
            entry = {"url": url, "from_cache": cached, "status": "ok", "product_id": None, "prices": 0, "error": None}
            try:
                matrix, context = default_configuration(html, url=url, observed_at=datetime.fromisoformat(fetched))
                entry["product_id"] = context["product_id"]
                cid = import_matrix(db, matrix, context, source=url)
                entry["prices"] = db.execute("SELECT count(*) FROM prices WHERE configuration_id=?", (cid,)).fetchone()[0]
                entry["configuration_id"] = cid
            except (MatrixError, ValueError, KeyError, TypeError) as exc:
                entry.update(status="failed", error=str(exc)[:300])
            with db:
                db.execute("INSERT OR REPLACE INTO product_pages VALUES (?,?,?,?,?,?,?,?)",
                           (url, fetched, entry["status"], entry["product_id"], entry.get("configuration_id"),
                            entry["prices"], entry["error"], now.isoformat()))
            report.append(entry)
    finally:
        db.close()
    return {"network_requests": state.get("requests", 0), "pages": report}


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", type=Path, default=ROOT / "data/catalog.sqlite3")
    cli.add_argument("--urls-from", type=Path, default=ROOT / "data/catalog.sqlite3",
                     help="database whose catalog_urls table lists the product URLs")
    cli.add_argument("--cache", type=Path, default=ROOT / "data/cache/products")
    cli.add_argument("--limit", type=int, help="only the first N product URLs (alphabetical)")
    cli.add_argument("url", nargs="*", help="explicit product URLs (overrides --limit)")
    args = cli.parse_args()
    chosen = args.url or product_urls(args.urls_from, args.limit)
    print(json.dumps(collect(args.db, chosen, args.cache), ensure_ascii=False, indent=1))
