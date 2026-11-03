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
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

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
            cost = Decimal(cells["C"]) if cells.get("C") else None
            valid = sale.is_finite() and sale > 0
        except (KeyError, ValueError, ArithmeticError):
            continue
        if blocks and valid:
            blocks[-1]["prices"][quantity] = (cost, sale)
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
        offers.replace_group(db, shop.PROVIDER, f"{shop.PAGES[0]}#%", items, stamp)  # one transaction: old and new
        offers.record_page(db, shop.PROVIDER, shop.PAGES[0], stamp, "ok", sum(len(i["rows"]) for i in items), None)
    finally:
        db.close()
    return {"products": len(items), "prices": sum(len(i["rows"]) for i in items)}


# The other sheets (bags, menus, coasters, pens, boxes, pads, folders, calendars, stickers) have the same idea with other layouts:
# one or more tables side by side, each with a header row ("UNIDADES", "MEDIDAS", "PVP PROVEEDOR", "PVP ICON"...) and titles
# between the rows. They are read by their headers, never by position.
SHEETS = {"BOLSAS papel": "Bolsas de papel", "CARTAS RESTAURANTE": "Cartas de restaurante", "MANTELES INDIVIDUALES": "Manteles individuales",
          "POSAVASOS": "Posavasos", "BOLIGRAFOS": "Bolígrafos", "CAJAS": "Cajas", "talonarios": "Talonarios", "CARPETAS": "Carpetas",
          "CALENDARIOS BOLSILLO": "Calendarios de bolsillo", "calendarios mesa wire-o": "Calendarios de mesa wire-o", "Adhesivos": "Adhesivos"}
PRICE_COLUMNS = {"icon": "PVP ICON en todas las hojas", "web": "PRECIO LA IMPRENTA DE INTERNET donde la hoja lo trae y PVP ICON en las demás"}
SHOP_SEARCH = f"{shop.SITE}/?s=%s&post_type=product"


def number(text: str | None) -> Decimal | None:
    try:
        value = Decimal((text or "").replace(",", ".").strip())
    except ArithmeticError:
        return None
    return value if value.is_finite() else None


def column_index(letters: str) -> int:
    total = 0
    for char in letters:
        total = total * 26 + ord(char) - 64
    return total


def tidy(label: str) -> str:
    """A block title without the supplier written next to it ("CARTA TRIPTICO (TRUYOL)") and on one line."""
    label = re.sub(r"\s*\((?:TRUYOL|ONLINE PRINTERS?|PRINT24|PRINTAI|STRICKER)\)", "", label, flags=re.I)
    label = " ".join(label.split()).strip(" .")
    if len(label) > 70:  # a pen's whole description is in the title cell: keep the start
        label = label[:70].rsplit(" ", 1)[0] + "…"
    return label


def parse_tables(rows: list[dict[str, str]], price: str = "icon") -> tuple[list[dict], list[str]]:
    """[{label, measure, prices: {quantity: price}}] and the problems found, from the rows of one sheet.

    Two tables with the same title and measure but different prices are a conflict: the first one is kept and it is reported.
    """
    groups: list[dict] = []
    found: dict[tuple, dict] = {}
    notes: list[str] = []
    header = None
    before: dict[str, str] = {}  # a title above the header row ("calendarios de bolsillo sin acabado") belongs to the first block
    for position, cells in enumerate(rows):
        if header is None:
            starts = [c for c, v in cells.items() if v.lower().startswith("unidades")]
            if not starts:
                before.update(cells)
                continue
            header = position
            ordered = sorted(starts, key=column_index)
            for number_, start in enumerate(ordered):
                end = column_index(ordered[number_ + 1]) if number_ + 1 < len(ordered) else 10**6
                span = {c: v.lower() for c, v in cells.items() if column_index(start) - 1 <= column_index(c) < end}
                pick = lambda test: next((c for c, v in span.items() if test(v)), None)
                label_col = next((c for c, v in span.items() if v == "producto" and column_index(c) < column_index(start)), start)
                icon = pick(lambda v: v.startswith("pvp icon") and "unitario" not in v)
                wanted = icon if price == "icon" else pick(lambda v: "imprenta" in v) or icon  # a table without our web column keeps the tariff price
                groups.append({"qty": start, "label": label_col, "measure": pick(lambda v: v.startswith("medidas")), "end": end,
                               "web": pick(lambda v: "imprenta" in v), "price": wanted, "title": tidy(before.get(label_col) or before.get(start) or ""), "number": number_ + 1})
            continue
        for column, text in cells.items():  # a sub-header between the header row and the data: "pvp la imprenta"
            if "imprenta" in text.lower() and not any(number(v) is not None for v in cells.values()):
                for group in groups:
                    if group["web"] is None and column_index(group["qty"]) - 1 <= column_index(column) < group["end"]:
                        group["web"] = column
                        if price == "web":
                            group["price"] = column
        for group in groups:
            qty_text = cells.get(group["qty"], "")
            separate = group["label"] != group["qty"]
            if separate and cells.get(group["label"]):
                group["title"] = tidy(cells[group["label"]])
            amount = number(cells.get(group["price"])) if group["price"] else None
            quantity = number(qty_text)
            if quantity is None:
                if qty_text and not separate and amount is None:
                    group["title"] = tidy(qty_text)
                continue
            if amount is None or amount <= 0:
                continue
            measure = (cells.get(group["measure"]) or "").strip() if group["measure"] else ""
            key = (group["title"], measure)
            block = found.setdefault(key, {"label": group["title"], "measure": measure, "prices": {}, "group": group["number"]})
            old = block["prices"].get(int(quantity))
            if old is not None and old != amount and block["group"] != group["number"]:
                notes.append(f"{group['title'] or 'sin título'} {measure} {int(quantity)} uds: dos tablas dan {old} y {amount}; me quedo con {old}")
            elif old is None:
                block["prices"][int(quantity)] = amount
    if header is None:
        raise ValueError("No encuentro una fila de títulos con «UNIDADES»")
    return list(found.values()), notes


def generic_products(sheet: str, blocks: list[dict]) -> list[dict]:
    name = SHEETS.get(sheet, sheet.title())
    query = quote(name.lower().split(" de ")[0])
    found = []
    for block in blocks:
        title = "" if block["label"].lower() == name.lower() else block["label"]  # "MANTELES INDIVIDUALES" under the sheet "Manteles individuales"
        label = " · ".join(x for x in (title, block["measure"]) if x)
        spec = ([{"group": "Formato", "label": block["measure"]}] if block["measure"] else []) + ([{"group": "Modelo", "label": block["label"]}] if block["label"] else [])
        rows = [{"quantity": q, "kind": "total", "price": amount, "currency": "EUR", "tax": "net", "shipping": "unknown",
                 "scope": "tarifa propia (Excel); precio sin IVA", "delivery_days": None} for q, amount in sorted(block["prices"].items())]
        found.append({"url": f"{SHOP_SEARCH % query}{TARIFF_MARK}{shop.slug(name + ' ' + label)}", "name": f"{name} · {label}" if label else name,
                      "rows": rows, "spec": spec, "sheet": sheet})
    return found


def load_rest(db_path: Path, excel: Path, price: str = "web", now: datetime | None = None) -> dict:
    """Load every other sheet as prices of our shop. Replaces what an earlier load stored for them."""
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    report, items = {}, []
    for sheet in SHEETS:
        try:
            rows = read_sheet(excel, sheet)
            blocks, notes = parse_tables(rows, price)
            used = price
            if price == "web":  # tables with no price of our web written keep the sheet's tariff; say which one was really used
                icon_blocks, _ = parse_tables(rows, "icon")
                if [b["prices"] for b in blocks] == [b["prices"] for b in icon_blocks]:
                    used = "icon"
        except ValueError as error:
            report[sheet] = {"products": 0, "prices": 0, "precio": price, "notes": [str(error)]}
            continue
        made = generic_products(sheet, blocks)
        items += made
        report[sheet] = {"products": len(made), "prices": sum(len(i["rows"]) for i in made), "precio": used, "notes": notes}
    if not items:  # a wrong Excel must not wipe the products already loaded
        raise ValueError("Ninguna hoja tiene precios; no cambio nada. " + "; ".join(f"{s}: {r['notes'][0]}" for s, r in report.items() if r["notes"])[:400])
    db = offers.connect(db_path)
    try:
        offers.replace_group(db, shop.PROVIDER, f"{shop.SITE}/?s=%{TARIFF_MARK}%", items, stamp)
    finally:
        db.close()
    return report


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("excel", type=Path)
    cli.add_argument("--db", type=Path, default=ROOT / "data/catalog.sqlite3")
    cli.add_argument("--hojas", choices=("tarjetas", "resto", "todas"), default="todas", help="qué hojas cargar")
    cli.add_argument("--precio", choices=tuple(PRICE_COLUMNS), default="web", help="columna de la hoja que se toma como precio de nuestra web: " + "; ".join(f"{k} = {v}" for k, v in PRICE_COLUMNS.items()))
    args = cli.parse_args()
    result = {}
    if args.hojas in ("tarjetas", "todas"):
        result["TARJETAS DE VISITA"] = load(args.db, args.excel)
    if args.hojas in ("resto", "todas"):
        result.update(load_rest(args.db, args.excel, args.precio))
    print(json.dumps(result, ensure_ascii=False, indent=1))
