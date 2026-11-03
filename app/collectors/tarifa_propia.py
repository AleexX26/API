"""Our own tariff: the sale prices (PVP) of our shop typed in an Excel sheet, loaded as the prices of La Imprenta de Internet.

The sheet "TARJETAS DE VISITA" has one block per product ("tarjetas 4/0 sin plastificar", ...) and, per quantity, the
supplier price ("pvp proveedor") and our sale price ("pvp icon"). Only our sale price goes to the comparator: net of VAT,
shipping to the peninsula included, standard delivery 7-10 days. The express delivery of the shop adds a fixed surcharge
(its configurator: "2-3 días +35€"), so each configuration is also loaded with the express price.

The Excel is read without extra libraries (an .xlsx is a zip of XML files). Loading it replaces what the browser reader
(laimprentadeinternet.py) stored for the business-card page; after that the browser reader skips that page.
"""
import html
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.collectors import laimprentadeinternet as shop
from app.collectors import offers

ROOT = Path(__file__).resolve().parents[2]
SHEET = "TARJETAS DE VISITA"
EXPRESS_SURCHARGE = Decimal("35")  # "2-3 días +35€" in the shop's configurator
SCOPE = "tarifa propia (Excel); precio sin IVA, envío a la península incluido"
STANDARD = [{"group": "Formato", "label": "85 x 55 mm"}, {"group": "Papel", "label": "350 g/m² papel estucado"}]
FINISHES = {"sin plastificar": "Sin acabado", "plastificado 1 cara": "Plastificado 1 cara", "plastificado 2 caras": "Plastificado 2 caras"}
DELIVERY = [("7-10 días", 10, Decimal(0)), ("2-3 días", 3, EXPRESS_SURCHARGE)]
TARIFF_MARK = "#tarifa-"


def read_sheet(path: Path, wanted: str = SHEET) -> list[dict[str, str]]:
    """The cells of one sheet as [{column letter: text}] per row (empty rows skipped)."""
    with zipfile.ZipFile(path) as book:
        strings = [html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
                   for si in re.findall(r"<si>(.*?)</si>", book.read("xl/sharedStrings.xml").decode("utf-8"), re.S)] \
            if "xl/sharedStrings.xml" in book.namelist() else []
        workbook = book.read("xl/workbook.xml").decode("utf-8")
        rels = book.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        sheets = re.findall(r'<sheet\b[^>]*?name="([^"]+)"[^>]*?r:id="([^"]+)"', workbook)
        match = next((rid for name, rid in sheets if wanted.lower() in html.unescape(name).lower()), None)
        if match is None:
            raise ValueError(f"No hay una hoja llamada «{wanted}». Hojas: {', '.join(html.unescape(n) for n, _ in sheets)}")
        tag = next(t for t in re.findall(r"<Relationship\b[^>]*>", rels) if f'Id="{match}"' in t)
        target = re.search(r'Target="([^"]+)"', tag).group(1)
        xml = book.read("xl/" + target.lstrip("/").removeprefix("xl/")).decode("utf-8")
    rows = []
    for body in re.findall(r"<row\b[^>]*>(.*?)</row>", xml, re.S):
        cells = {}
        for column, attrs, inner in re.findall(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', body, re.S):
            value = re.search(r"<v>(.*?)</v>", inner or "", re.S)
            if value is None:
                inline = re.search(r"<t[^>]*>(.*?)</t>", inner or "", re.S)
                if inline:
                    cells[column] = html.unescape(inline.group(1)).strip()
                continue
            text = value.group(1)
            cells[column] = (strings[int(text)] if 't="s"' in attrs else html.unescape(text)).strip()
        if cells:
            rows.append(cells)
    return rows


def parse_tariff(rows: list[dict[str, str]]) -> list[dict]:
    """[{label, sides, finish, prices: {quantity: (supplier cost or None, sale price)}}] from the sheet's rows."""
    blocks: list[dict] = []
    for cells in rows:
        label = cells.get("A", "").strip()
        if label and not label.upper().startswith(("TARJETAS DE VISITA", "PRODUCTO")):
            text = " ".join(label.lower().split())
            sides = 1 if "4/0" in text else 2 if "4/4" in text else None
            finish = next((name for key, name in FINISHES.items() if key in text), None)
            if sides is None or finish is None:
                raise ValueError(f"No entiendo el producto «{label}» (esperaba 4/0 o 4/4 y «sin plastificar» o «plastificado 1/2 caras»)")
            blocks.append({"label": label, "sides": sides, "finish": finish, "prices": {}})
        try:
            quantity, sale = int(float(cells["B"])), Decimal(cells["D"])
        except (KeyError, ValueError, ArithmeticError):
            continue
        if blocks and sale > 0:
            cost = cells.get("C")
            blocks[-1]["prices"][quantity] = (Decimal(cost) if cost else None, sale)
    return [b for b in blocks if b["prices"]]


def products(blocks: list[dict]) -> list[dict]:
    found = []
    for block in blocks:
        for delivery, days, surcharge in DELIVERY:
            sides = "1 cara" if block["sides"] == 1 else "2 caras"
            names = [sides, block["finish"], delivery]
            spec = STANDARD + [{"group": "Impresión", "label": "4+0 una cara" if block["sides"] == 1 else "4+4 dos caras"},
                               {"group": "Acabados", "label": "sin acabado" if block["finish"].startswith("Sin") else block["finish"]},
                               {"group": "Revisión de tu diseño", "label": "revisión gratis"},
                               {"group": "Plazo de producción", "label": f"{delivery} hábiles"}]
            rows = [{"quantity": q, "kind": "total", "price": sale + surcharge, "currency": "EUR", "tax": "net", "shipping": "included",
                     "scope": SCOPE, "delivery_days": days} for q, (_, sale) in sorted(block["prices"].items())]
            label = " · ".join(names)
            found.append({"url": f"{shop.PAGES[0]}{TARIFF_MARK}{shop.slug(label)}", "name": f"Tarjetas de Visita · {label}", "rows": rows, "spec": spec})
    return found


def load(db_path: Path, excel: Path, now: datetime | None = None) -> dict:
    """Replace the shop's business-card prices by the sheet's. Returns what was loaded."""
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    items = products(parse_tariff(read_sheet(excel)))
    if not items:
        raise ValueError("La hoja no tiene ningún precio de venta (columna «pvp icon»)")
    db = offers.connect(db_path)
    try:
        with db:  # one transaction: the old business-card products of the page and the new ones
            db.execute("DELETE FROM supplier_offers WHERE provider=? AND product_url LIKE ?", (shop.PROVIDER, f"{shop.PAGES[0]}#%"))
        for item in items:
            offers.replace_offers(db, shop.PROVIDER, item["url"], item["name"], item["rows"], stamp, item["spec"])
        offers.record_page(db, shop.PROVIDER, shop.PAGES[0], stamp, "ok", sum(len(i["rows"]) for i in items), None)
    finally:
        db.close()
    return {"products": len(items), "prices": sum(len(i["rows"]) for i in items)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Uso: python -m app.collectors.tarifa_propia ARCHIVO.xlsx [base.sqlite3]")
    db = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data/catalog.sqlite3"
    print(json.dumps(load(db, Path(sys.argv[1])), ensure_ascii=False, indent=1))
