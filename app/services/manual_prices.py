"""Prices typed in by hand from a provider's web (the ones the collectors cannot read, e.g. 350 g at Onlineprinters).

They live in the workbench database, apart from the collected data, and are shown in the catalog as one more product
marked "anotado a mano": the filters treat them like any other page, so an exact one wins over a "closest" one.
"""
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

SIDES_LABEL = {1: "4+0 una cara", 2: "4+4 dos caras"}


def init(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS manual_prices (
          id INTEGER PRIMARY KEY, provider TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL, format TEXT NOT NULL,
          grams INTEGER, paper_type TEXT NOT NULL, surface TEXT NOT NULL, sides INTEGER NOT NULL, finishing TEXT NOT NULL,
          quantity INTEGER NOT NULL, price TEXT NOT NULL, tax TEXT NOT NULL, shipping TEXT NOT NULL,
          delivery_days INTEGER, note TEXT NOT NULL, created_at TEXT NOT NULL)""")


def add(path: Path, data: dict) -> int:
    with sqlite3.connect(path) as db:
        cursor = db.execute("""INSERT INTO manual_prices (provider,title,url,format,grams,paper_type,surface,sides,finishing,quantity,
            price,tax,shipping,delivery_days,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (data["provider"], data["title"], data["url"], data["format"], data["grams"], data["paper_type"], data["surface"],
                             data["sides"], data["finishing"], data["quantity"], str(data["price"]), data["tax"], data["shipping"],
                             data["delivery_days"], data["note"], datetime.now(timezone.utc).isoformat()))
        return cursor.lastrowid


def update(path: Path, price_id: int, data: dict) -> bool:
    """Change a price typed in earlier; the date becomes today's (the price was looked at again)."""
    with sqlite3.connect(path) as db:
        return db.execute("""UPDATE manual_prices SET provider=?,title=?,url=?,format=?,grams=?,paper_type=?,surface=?,sides=?,finishing=?,
            quantity=?,price=?,tax=?,shipping=?,delivery_days=?,note=?,created_at=? WHERE id=?""",
                          (data["provider"], data["title"], data["url"], data["format"], data["grams"], data["paper_type"], data["surface"],
                           data["sides"], data["finishing"], data["quantity"], str(data["price"]), data["tax"], data["shipping"],
                           data["delivery_days"], data["note"], datetime.now(timezone.utc).isoformat(), price_id)).rowcount > 0


def add_many(path: Path, data: dict, items: list[dict]) -> list[int]:
    """The same configuration at several quantities, all or none."""
    ids = []
    with sqlite3.connect(path) as db:
        for item in items:
            ids.append(db.execute("""INSERT INTO manual_prices (provider,title,url,format,grams,paper_type,surface,sides,finishing,quantity,
                price,tax,shipping,delivery_days,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                  (data["provider"], data["title"], data["url"], data["format"], data["grams"], data["paper_type"], data["surface"],
                                   data["sides"], data["finishing"], item["quantity"], str(item["price"]), data["tax"], data["shipping"],
                                   data["delivery_days"], data["note"], datetime.now(timezone.utc).isoformat())).lastrowid)
    return ids


def remove(path: Path, price_id: int) -> bool:
    with sqlite3.connect(path) as db:
        return db.execute("DELETE FROM manual_prices WHERE id=?", (price_id,)).rowcount > 0


def rows(path: Path | None) -> list[dict]:
    if path is None or not Path(path).exists():
        return []
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in db.execute("SELECT * FROM manual_prices ORDER BY created_at DESC, id DESC")]
        except sqlite3.OperationalError:
            return []


def spec_of(row: dict) -> list[dict]:
    """The characteristics as the collected pages name them, so the card filters read them the same way."""
    spec = []
    if row["format"]:
        spec.append({"group": "Formato", "label": row["format"]})
    paper = " ".join(x for x in (f"{row['grams']} g/m²" if row["grams"] else "", row["paper_type"]) if x)
    if paper:
        spec.append({"group": "Papel", "label": paper})
    if row["surface"]:
        spec.append({"group": "Realización", "label": row["surface"].lower()})
    spec.append({"group": "Impresión", "label": SIDES_LABEL.get(row["sides"], "")})
    spec.append({"group": "Acabados", "label": "sin acabado" if row["finishing"].lower().startswith("sin") else row["finishing"]})
    if row["delivery_days"]:
        spec.append({"group": "Plazo de producción", "label": f"{row['delivery_days']} días hábiles"})
    return [x for x in spec if x["label"]]


def items(path: Path | None, names: dict[str, str]) -> list[dict]:
    """Catalog products: one per (page, characteristics), with a price tier for each quantity typed in."""
    groups: dict[tuple, list[dict]] = {}
    for row in rows(path):
        key = (row["provider"], row["url"], json.dumps(spec_of(row), ensure_ascii=False), row["tax"], row["shipping"])
        groups.setdefault(key, []).append(row)
    found = []
    for (provider, url, _, tax, shipping), group in groups.items():
        latest = {}
        for row in sorted(group, key=lambda r: r["id"]):  # a later note for the same quantity replaces the earlier one
            latest[row["quantity"]] = row
        tiers = sorted(latest.values(), key=lambda r: r["quantity"])
        cheapest = min(tiers, key=lambda r: Decimal(r["price"]))
        first = group[0]
        found.append({"provider": provider, "provider_name": names.get(provider, provider), "title": first["title"], "url": url,
                      "price_kind": "total", "tax_status": tax, "shipping": shipping, "comparable": True,
                      "scope": "precio anotado a mano desde la web del proveedor", "from_price": cheapest["price"],
                      "from_quantity": cheapest["quantity"], "min_quantity": tiers[0]["quantity"], "max_quantity": tiers[-1]["quantity"],
                      "tiers": len(tiers), "variants": 0, "observed_at": max(r["created_at"] for r in group),
                      "prices": [[t["quantity"], t["price"], t["delivery_days"], t["delivery_days"]] for t in tiers],
                      "spec": spec_of(first), "manual": True, "manual_ids": [t["id"] for t in tiers],
                      "manual_note": "; ".join(sorted({t["note"] for t in tiers if t["note"]}))})
    return found
