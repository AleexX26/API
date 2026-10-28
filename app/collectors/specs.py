"""Readable default-configuration labels for collected Print24 pages. Offline: reads the page cache.

Fills `product_specs(url, spec_json)` so the web can show what a default price refers to
(format, paper, inks...) instead of bare option ids.
"""
import json
import sqlite3
from pathlib import Path

from app.collectors.products import cache_name
from app.parsers.price_matrix import MatrixError
from app.parsers.product_page import SPANNED, calculation_data

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "CREATE TABLE IF NOT EXISTS product_specs (url TEXT PRIMARY KEY, spec_json TEXT NOT NULL);"


def default_spec(data: dict) -> list[dict]:
    """[{group, label}] for the visible, non-spanned groups of the default selection."""
    master = data["itemMaster"]
    selected = {p["name"]: str(p["id"]) for p in master["selectedProps"]}
    spec = []
    for box in master["boxes"]:
        name = box["propGroupName"]
        if box.get("hide") or name in SPANNED | {"proofpages"} or name not in selected:
            continue
        for prop in box["properties"]:
            if str(prop["pgrId"]) == selected[name]:
                label = " ".join(part.strip() for part in prop["propertyTranslated"] if part and part.strip())
                if label:
                    spec.append({"group": (box.get("boxTitleTranslated") or name).strip(), "label": label})
                break
    return spec


def fill(db_path: Path, cache_dir: Path) -> dict:
    db = sqlite3.connect(db_path)
    done = skipped = 0
    try:
        db.execute(SCHEMA)
        urls = [r[0] for r in db.execute("SELECT url FROM product_pages WHERE status='ok'")]
        for url in urls:
            file = cache_dir / cache_name(url)
            try:
                spec = default_spec(calculation_data(file.read_text(encoding="utf-8")))
            except (OSError, MatrixError, KeyError, TypeError):
                skipped += 1
                continue
            with db:
                db.execute("INSERT OR REPLACE INTO product_specs VALUES (?,?)", (url, json.dumps(spec, ensure_ascii=False)))
            done += 1
    finally:
        db.close()
    return {"specs": done, "skipped": skipped}


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", type=Path, default=ROOT / "data/catalog.sqlite3")
    cli.add_argument("--cache", type=Path, default=ROOT / "data/cache/products")
    args = cli.parse_args()
    print(json.dumps(fill(args.db, args.cache)))
