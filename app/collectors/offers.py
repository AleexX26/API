"""Shared storage for supplier prices read from public product pages (every provider except Print24).

One row per product / variant / quantity. `price_kind` says what the price means:
  'unit'  -> price per unit for that quantity tier (TusKamisetas)
  'total' -> price of the whole order of that quantity (Onlineprinters, Printai)
`tax_status` ('net' | 'gross' | 'unknown') and `shipping` ('included' | 'excluded' | 'unknown') are stored
exactly as far as the page itself says; nothing is assumed.
"""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS supplier_offers (
  provider TEXT NOT NULL, product_url TEXT NOT NULL, product_name TEXT NOT NULL, group_label TEXT NOT NULL,
  variant TEXT NOT NULL, quantity INTEGER NOT NULL, price_kind TEXT NOT NULL CHECK(price_kind IN ('unit','total')),
  price TEXT NOT NULL, currency TEXT NOT NULL, tax_status TEXT NOT NULL CHECK(tax_status IN ('net','gross','unknown')),
  shipping TEXT NOT NULL CHECK(shipping IN ('included','excluded','unknown')), scope TEXT NOT NULL,
  delivery_days INTEGER, spec_json TEXT NOT NULL, observed_at TEXT NOT NULL,
  PRIMARY KEY (provider, product_url, group_label, variant, quantity));
CREATE INDEX IF NOT EXISTS idx_supplier_offers_provider ON supplier_offers(provider, product_name);
CREATE TABLE IF NOT EXISTS supplier_pages (
  provider TEXT NOT NULL, url TEXT NOT NULL, fetched_at TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('ok','failed')),
  tiers INTEGER, error TEXT, PRIMARY KEY (provider, url));
"""


def connect(path: Path) -> sqlite3.Connection:
    """Several collectors may write the same database at once: WAL plus a long busy timeout keep them from colliding."""
    db = sqlite3.connect(path, timeout=60)
    db.execute("PRAGMA busy_timeout=60000")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    return db


def replace_offers(db: sqlite3.Connection, provider: str, url: str, name: str, rows: list[dict],
                   observed_at: str, spec: list[dict] | None = None) -> None:
    """Replace everything stored for this product page in one transaction."""
    spec_json = json.dumps(spec or [], ensure_ascii=False)
    with db:
        db.execute("DELETE FROM supplier_offers WHERE provider=? AND product_url=?", (provider, url))
        db.executemany(
            "INSERT INTO supplier_offers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(provider, url, name, r.get("group", ""), r.get("variant", ""), r["quantity"], r["kind"], str(r["price"]),
              r["currency"], r["tax"], r["shipping"], r["scope"], r.get("delivery_days"), spec_json, observed_at)
             for r in rows])


def record_page(db: sqlite3.Connection, provider: str, url: str, fetched_at: str, status: str, count: int, error: str | None) -> None:
    with db:
        db.execute("INSERT OR REPLACE INTO supplier_pages VALUES (?,?,?,?,?,?)", (provider, url, fetched_at, status, count, error))
