"""Download the Spanish catalog sitemaps (category, product, variant) into SQLite.

Bounded like discovery: robots.txt is checked first, 5 s between network requests, no
redirects, no retries, no cookies. Raw XML is cached on disk so a rerun inside the cache
window makes no request. Any error stops the run (nothing is skipped silently).
"""
import hashlib
import json
import sqlite3
import ssl
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import HTTPSHandler, Request, build_opener
from xml.etree import ElementTree

import certifi

from app.collectors.discovery import AGENT, ORIGIN, NoRedirect, allowed, spanish_url

ROOT = Path(__file__).resolve().parents[2]
SITEMAPS = {
    "category": ORIGIN + "/es/sitemap_category.xml",
    "product": ORIGIN + "/es/sitemap_product.xml",
    "productvariant": ORIGIN + "/es/sitemap_productvariant.xml",
}
DEFAULT_ROBOTS = ROOT / "data/discovery-20261027-01/robots.txt"
LIMIT = 50_000_000  # sitemap protocol maximum (uncompressed)
PAUSE = 5
CACHE_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS sitemap_fetches (
  kind TEXT PRIMARY KEY, url TEXT NOT NULL, fetched_at TEXT NOT NULL,
  sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, locs_total INTEGER NOT NULL,
  locs_in_scope INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS catalog_urls (
  url TEXT PRIMARY KEY, kind TEXT NOT NULL, lastmod TEXT,
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_catalog_urls_kind ON catalog_urls(kind);
"""


def parse_urlset(raw: bytes) -> tuple[list[tuple[str, str | None]], int]:
    """Return ([(url, lastmod)] in the /es scope, total <loc> count)."""
    root = ElementTree.fromstring(raw)
    if root.tag.rsplit("}", 1)[-1] != "urlset":
        raise ValueError("Unexpected sitemap document: expected urlset")
    found, total = {}, 0
    for entry in root:
        loc = lastmod = None
        for child in entry:
            name = child.tag.rsplit("}", 1)[-1]
            if name == "loc" and child.text:
                loc = child.text.strip()
            elif name == "lastmod" and child.text:
                lastmod = child.text.strip()
        if loc:
            total += 1
            if spanish_url(loc):
                found.setdefault(loc, lastmod)
    return sorted(found.items()), total


def fetch_cached(url: str, cache_file: Path, now: datetime, state: dict, max_age_days: int = CACHE_DAYS,
                 expected: str = "xml") -> tuple[bytes, bool]:
    """Return (raw, from_cache). Network requests are spaced PAUSE seconds apart."""
    meta_file = cache_file.with_suffix(".json")
    if cache_file.exists() and meta_file.exists():
        fetched = datetime.fromisoformat(json.loads(meta_file.read_text(encoding="utf-8"))["fetched_at"])
        if now - fetched < timedelta(days=max_age_days):
            return cache_file.read_bytes(), True
    if state.get("requests"):
        time.sleep(PAUSE)
    state["requests"] = state.get("requests", 0) + 1
    # certificates are always verified; certifi's list also knows roots (Sectigo R46, Truyol) missing from some Python installs
    url = quote(url, safe=":/?&=%#+@,;~!$'()*[]")  # a sitemap may list accents (piñata) that http.client cannot send as they are
    context = ssl.create_default_context(cafile=certifi.where())
    with build_opener(NoRedirect(), HTTPSHandler(context=context)).open(Request(url, headers={"User-Agent": AGENT}), timeout=60) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        raw = response.read(LIMIT + 1)
        status = response.status
    if status != 200 or expected not in content_type:
        raise ValueError(f"Unexpected response {status} {content_type!r}; stop for review")
    if len(raw) > LIMIT:
        raise ValueError("Sitemap exceeds size limit")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(raw)
    meta_file.write_text(json.dumps({"url": url, "fetched_at": now.isoformat(), "status": status,
                                     "content_type": content_type, "sha256": hashlib.sha256(raw).hexdigest()}),
                         encoding="utf-8")
    return raw, False


def collect(db_path: Path, cache_dir: Path, robots_file: Path = DEFAULT_ROBOTS,
            sitemaps: dict[str, str] | None = None, now: datetime | None = None) -> dict:
    sitemaps = sitemaps or SITEMAPS
    now = now or datetime.now(timezone.utc)
    robots = robots_file.read_text(encoding="utf-8-sig")
    for url in sitemaps.values():
        if not allowed(robots, url):
            raise ValueError(f"robots.txt does not permit {url}")
    state: dict = {}
    parsed = {}
    for kind, url in sitemaps.items():
        raw, cached = fetch_cached(url, cache_dir / f"sitemap_{kind}.xml", now, state)
        urls, total = parse_urlset(raw)
        parsed[kind] = (url, raw, urls, total, cached)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = now.isoformat()
    db = sqlite3.connect(db_path)
    try:
        with db:  # one transaction: all three sitemaps or none
            db.executescript(SCHEMA)
            for kind, (url, raw, urls, total, _) in parsed.items():
                db.execute("INSERT OR REPLACE INTO sitemap_fetches VALUES (?,?,?,?,?,?,?)",
                           (kind, url, stamp, hashlib.sha256(raw).hexdigest(), len(raw), total, len(urls)))
                db.executemany(
                    "INSERT INTO catalog_urls(url,kind,lastmod,first_seen,last_seen) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(url) DO UPDATE SET kind=excluded.kind,lastmod=excluded.lastmod,last_seen=excluded.last_seen",
                    [(u, kind, lm, stamp, stamp) for u, lm in urls])
    finally:
        db.close()
    return {"network_requests": state.get("requests", 0),
            "sitemaps": {k: {"urls": len(v[2]), "locs_total": v[3], "from_cache": v[4]} for k, v in parsed.items()}}


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", type=Path, default=ROOT / "data/catalog.sqlite3")
    cli.add_argument("--cache", type=Path, default=ROOT / "data/cache/sitemaps")
    args = cli.parse_args()
    print(json.dumps(collect(args.db, args.cache), indent=2))
