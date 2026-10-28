"""Atomic offline imports. Context is our own format, NOT a provider response."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.parsers.price_matrix import identifier, parse_matrix


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(Path(__file__).parents[1].joinpath("database/schema.sql").read_text())
    return db


def timestamp(value: str) -> str:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("Timestamps require a timezone")
    return dt.astimezone(timezone.utc).isoformat()


def canonical_context(context: dict[str, Any]) -> str:
    props = context["properties"]
    if not isinstance(props, list) or not props:
        raise ValueError("Explicit configuration options required")
    normalized = [{"name": identifier(p["name"]), "id": identifier(p["id"])} for p in props]
    if len({p["name"] for p in normalized}) != len(normalized):
        raise ValueError("Repeated property group")
    for key in ("country", "currency", "account_scope", "validity_evidence"):
        identifier(context[key])
    if len(context["country"]) != 2 or len(context["currency"]) != 3:
        raise ValueError("Explicit country and currency codes required")
    if not isinstance(context["services"], dict):
        raise ValueError("Explicit services object required")
    return json.dumps({"product_id": identifier(context["product_id"]),
                       "properties": sorted(normalized, key=lambda p: p["name"]),
                       "country": context["country"], "currency": context["currency"],
                       "account_scope": context["account_scope"], "services": context["services"]},
                      sort_keys=True, separators=(",", ":"), allow_nan=False)


def import_matrix(db: sqlite3.Connection, raw: str, context: dict[str, Any], *, source: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    with db:
        run = db.execute("INSERT INTO sync_runs(started_at,status,source,source_sha256) VALUES (?,?,?,?)",
                         (now, "running", source, hashlib.sha256(raw.encode()).hexdigest())).lastrowid
    try:
        offers = parse_matrix(raw)
        canonical = canonical_context(context)
        identity = json.loads(canonical)
        cid = hashlib.sha256(canonical.encode()).hexdigest()
        observed = timestamp(context["observed_at"])
        expires = timestamp(context["valid_until"])
        if expires <= observed:
            raise ValueError("valid_until must follow observed_at")
        with db:
            db.execute("INSERT OR IGNORE INTO products(source_id) VALUES (?)", (identity["product_id"],))
            pid = db.execute("SELECT id FROM products WHERE source_id=?", (identity["product_id"],)).fetchone()[0]
            db.execute("INSERT OR IGNORE INTO configurations VALUES (?,?,?,?,?,?,?,?)",
                       (cid, pid, identity["country"], identity["currency"], identity["account_scope"],
                        json.dumps(identity["services"], sort_keys=True), canonical, context["validity_evidence"]))
            for prop in identity["properties"]:
                db.execute("INSERT OR IGNORE INTO property_groups(source_name) VALUES (?)", (prop["name"],))
                gid = db.execute("SELECT id FROM property_groups WHERE source_name=?", (prop["name"],)).fetchone()[0]
                db.execute("INSERT OR IGNORE INTO property_options(group_id,source_id) VALUES (?,?)", (gid, prop["id"]))
                oid = db.execute("SELECT id FROM property_options WHERE group_id=? AND source_id=?", (gid, prop["id"])).fetchone()[0]
                db.execute("INSERT OR IGNORE INTO product_property_options VALUES (?,?)", (pid, oid))
                db.execute("INSERT OR IGNORE INTO configuration_options VALUES (?,?)", (cid, oid))
            for offer in offers:
                db.execute("INSERT OR IGNORE INTO quantities(product_id,source_id,value) VALUES (?,?,?)", (pid, offer.quantity_id, offer.quantity_value))
                qid = db.execute("SELECT id FROM quantities WHERE product_id=? AND source_id=? AND value=?", (pid, offer.quantity_id, offer.quantity_value)).fetchone()[0]
                db.execute("INSERT OR IGNORE INTO shipping_options(source_id) VALUES (?)", (offer.delivery_type,))
                sid = db.execute("SELECT id FROM shipping_options WHERE source_id=?", (offer.delivery_type,)).fetchone()[0]
                old = db.execute("SELECT * FROM prices WHERE configuration_id=? AND quantity_id=? AND shipping_option_id=?", (cid, qid, sid)).fetchone()
                values = {"product_net": str(offer.product_net), "total_net": str(offer.total_net),
                          "total_gross": str(offer.total_gross), "shipping_net": str(offer.shipping_net),
                          "shipping_gross": None, "total_vat": str(offer.total_vat),
                          "unit_product_net": str(offer.unit_product_net), "delivery_days": offer.delivery_days,
                          "delivery_text": offer.delivery_text, "observed_at": observed,
                          "imported_at": now, "valid_until": expires, "run_id": run}
                if old:
                    if observed < old["observed_at"]:
                        raise ValueError("An older observation cannot overwrite a newer price")
                    same = all(old[k] == v for k, v in values.items() if k not in ("imported_at", "run_id"))
                    if same:
                        continue
                    if observed == old["observed_at"]:
                        raise ValueError("Conflicting data for the same observation time")
                    db.execute("INSERT INTO price_history(price_id,old_snapshot_json,replaced_at,replacement_run_id) VALUES (?,?,?,?)",
                               (old["id"], json.dumps(dict(old)), now, run))
                    db.execute("UPDATE prices SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?", (*values.values(), old["id"]))
                else:
                    values = {"configuration_id": cid, "quantity_id": qid, "shipping_option_id": sid, **values}
                    db.execute("INSERT INTO prices (" + ",".join(values) + ") VALUES (" + ",".join("?" for _ in values) + ")", tuple(values.values()))
            db.execute("UPDATE sync_runs SET status='success',finished_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), run))
        return cid
    except Exception as exc:
        with db:
            db.execute("UPDATE sync_runs SET status='failed',finished_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), run))
            db.execute("INSERT INTO sync_errors(run_id,message) VALUES (?,?)", (run, str(exc)))
        raise
