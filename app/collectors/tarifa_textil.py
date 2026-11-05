"""Our tariff for what the shop's web cannot tell: T-shirts and hooded sweatshirts (sheet TEXTIL) and mugs (sheet MERCHAN) of the
2024 workbook "precios la imprenta de internet".

These pages have no quantity select in the shop, so the browser reader cannot get a price from them. The workbook is a working file
(several years of columns, some sheets with older supplier costs), so only the two columns that are clean in these sheets are read:
"PVP prov." (what the supplier charges) and "nuevo PVP tienda" (the new shop price = cost + profit). The price is stored as the shop
price of that page, net of VAT, shipping not confirmed, and the supplier cost goes to `own_costs`, so that the margin shows on the card.
It is NOT confirmed against the live shop (its pages show no price): the scope says so. Products that the shop's configurators already
give (ballpoint pens, bottles, lanyards, caps) are left out: the browser reader has the real price of each combination.
"""
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.collectors import laimprentadeinternet as shop
from app.collectors import offers
from app.collectors.tarifa_propia import number, read_sheet

MARK = "#tarifa-textil-"
SCOPE = "tarifa propia (Excel 2024, «nuevo PVP tienda»); sin IVA; envío sin confirmar; sin confirmar en la web"
# (what the label starts with, the page of the shop) for each sheet; anything else in the sheet is not loaded
TEXTIL = {"camisetas": f"{shop.SITE}/impresion-de-camisetas/", "sudaderas": f"{shop.SITE}/sudaderas-personalizadas/"}
MERCHAN = {"tazas": f"{shop.SITE}/tazas/"}
# TEXTIL holds two tables side by side: label, quantity, supplier, cost, price columns of each
TEXTIL_SIDES = [dict(label="A", qty="B", supplier="C", cost="D", price="E"), dict(label="I", qty="J", supplier="K", cost="L", price="M")]
MERCHAN_SIDES = [dict(label="A", qty="B", supplier=None, cost="C", price="D")]
TECHNIQUE = re.compile(r"\b(serigraf[ií]a(?: \d+ color(?:es)?)?|digital a color|sublimaci[oó]n(?: a color)?|dtf)\b", re.I)


def blocks_of(rows: list[dict], sides: list[dict]) -> list[dict]:
    """[{label, rows: [{quantity, cost, price, supplier}]}] for every table (a block starts at a row with a label)."""
    found: list[dict] = []
    for side in sides:
        current = None
        for row in rows:
            quantity = number(row.get(side["qty"]))
            if (row.get(side["qty"]) or "").strip().lower() == "cantidad":
                continue  # header row
            label = (row.get(side["label"]) or "").strip()
            if label and quantity is None:
                current = None  # a title row with no quantity (header text, COMPLEMENTOS...)
            if label and quantity is not None:
                current = {"label": label, "rows": []}
                found.append(current)
            if current is None or quantity is None or quantity <= 0 or quantity != quantity.to_integral_value():
                continue
            price, cost = number(row.get(side["price"])), number(row.get(side["cost"]))
            if price is None or price <= 0 or cost is None or cost <= 0:
                continue
            current["rows"].append({"quantity": int(quantity), "cost": cost, "price": price,
                                    "supplier": (row.get(side["supplier"]) or "").strip() if side["supplier"] else ""})
    return found


def coherence(block: dict) -> list[str]:
    """Problems that make a block unsafe to load: repeated quantity, or a price that goes DOWN when the quantity goes up."""
    problems = []
    quantities = [r["quantity"] for r in block["rows"]]
    if len(set(quantities)) != len(quantities):
        problems.append("cantidades repetidas")
    ordered = sorted(block["rows"], key=lambda r: r["quantity"])
    if any(b["price"] < a["price"] for a, b in zip(ordered, ordered[1:])):
        problems.append("el precio baja al subir la cantidad")
    if any(r["price"] < r["cost"] for r in block["rows"]):
        problems.append("precio por debajo del coste")
    return problems


def spec_of(label: str, family: str) -> list[dict]:
    technique = TECHNIQUE.search(label)
    zone = label[technique.end():].strip(" ,-") if technique else ""
    garment = label[:technique.start()].strip(" ,-") if technique else label
    return [x for x in ({"group": "Prenda" if family == "textil" else "Producto", "label": garment.capitalize()},
                        {"group": "Impresión", "label": technique.group(0).lower()} if technique else {}, {"group": "Zona de impresión", "label": zone} if zone else {}) if x]


def products_of(blocks: list[dict], pages: dict[str, str], family: str) -> tuple[list[dict], list[str]]:
    items, notes = [], []
    for block in blocks:
        page = next((url for start, url in pages.items() if block["label"].lower().startswith(start)), None)
        if page is None:
            notes.append(f"«{block['label'][:50]}»: no se carga (lo lee el configurador de la web o no hay ficha)")
            continue
        if not block["rows"]:
            notes.append(f"«{block['label'][:50]}»: sin precios")
            continue
        problems = coherence(block)
        if problems:
            notes.append(f"«{block['label'][:50]}»: no se carga ({', '.join(problems)})")
            continue
        slug = shop.slug(block["label"])[:90]
        suppliers = sorted({r["supplier"] for r in block["rows"] if r["supplier"]})
        spec = spec_of(block["label"], family) + ([{"group": "Proveedor del coste", "label": ", ".join(suppliers)}] if suppliers else [])
        ordered = sorted(block["rows"], key=lambda r: r["quantity"])
        items.append({"url": f"{page}{MARK}{slug}", "name": block["label"][:1].upper() + block["label"][1:], "spec": spec,
                      "costs": {r["quantity"]: r["cost"] for r in ordered},
                      "rows": [{"quantity": r["quantity"], "kind": "total", "price": r["price"], "currency": "EUR", "tax": "net",
                                "shipping": "unknown", "scope": SCOPE, "delivery_days": None} for r in ordered]})
    return items, notes


def load(db_path: Path, excel: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    items, notes = [], []
    for sheet, sides, pages, family in (("TEXTIL", TEXTIL_SIDES, TEXTIL, "textil"), ("MERCHAN", MERCHAN_SIDES, MERCHAN, "merchan")):
        found, sheet_notes = products_of(blocks_of(read_sheet(excel, sheet), sides), pages, family)
        items += found
        notes += [f"{sheet}: {n}" for n in sheet_notes]
    if not items:  # a wrong Excel must not wipe what is already loaded
        raise ValueError("Ningún bloque de TEXTIL ni de MERCHAN tiene precios; no cambio nada. " + "; ".join(notes)[:300])
    db = offers.connect(db_path)
    try:
        offers.replace_group(db, shop.PROVIDER, [f"{shop.SITE}/%{MARK}%"], items, now.isoformat())
    finally:
        db.close()
    return {"products": len(items), "prices": sum(len(i["rows"]) for i in items), "pages": sorted({i["url"].split("#")[0] for i in items}), "notes": notes}
