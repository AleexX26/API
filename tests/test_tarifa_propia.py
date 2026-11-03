import sqlite3
import zipfile
from decimal import Decimal

import pytest

from app.collectors import laimprentadeinternet as shop
from app.collectors import tarifa_propia as tariff

ROWS = [
    ["TARJETAS DE VISITA  (PRINT24)"],
    ["PRODUCTO", "unidades", "pvp proveedor", "pvp icon"],
    ["tarjetas 4/0  sin plastificar ", 100, 10, 30],
    ["", 250, 10.5, 31],
    ["", 750, 15, None],  # no sale price: not loaded
    ["tarjeta 4/4 plastificado 2 caras", 100, 20, 50],
]


def make_excel(path, rows=ROWS, sheet_name="TARJETAS DE VISITA"):
    """A minimal .xlsx: text in shared strings, numbers as they are."""
    strings, body = [], []
    for number, row in enumerate(rows, start=1):
        cells = []
        for column, value in zip("ABCD", row):
            if value is None or value == "":
                continue
            if isinstance(value, str):
                strings.append(value)
                cells.append(f'<c r="{column}{number}" t="s"><v>{len(strings) - 1}</v></c>')
            else:
                cells.append(f'<c r="{column}{number}"><v>{value}</v></c>')
        body.append(f'<row r="{number}">{"".join(cells)}</row>')
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("xl/workbook.xml", f'<workbook xmlns:r="x"><sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets></workbook>')
        book.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="rId1" Type="t" Target="worksheets/sheet1.xml"/></Relationships>')
        book.writestr("xl/sharedStrings.xml", "<sst>" + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        book.writestr("xl/worksheets/sheet1.xml", f'<worksheet><sheetData>{"".join(body)}</sheetData></worksheet>')


def test_the_sheet_is_read_by_blocks_and_only_sale_prices_with_a_value_count(tmp_path):
    excel = tmp_path / "tarifa.xlsx"
    make_excel(excel)
    blocks = tariff.parse_tariff(tariff.read_sheet(excel))
    assert [(b["sides"], b["finish"]) for b in blocks] == [(1, "Sin acabado"), (2, "Plastificado 2 caras")]
    assert blocks[0]["prices"] == {100: (Decimal("10"), Decimal("30")), 250: (Decimal("10.5"), Decimal("31"))}  # 750 has no sale price


def test_an_unknown_product_name_stops_instead_of_guessing(tmp_path):
    excel = tmp_path / "tarifa.xlsx"
    make_excel(excel, [["tarjetas redondas mate", 100, 10, 30]])
    with pytest.raises(ValueError, match="No entiendo"):
        tariff.parse_tariff(tariff.read_sheet(excel))
    with pytest.raises(ValueError, match="No hay una hoja"):
        tariff.read_sheet(excel, "OTRA HOJA")


def test_loading_replaces_the_browser_prices_and_adds_the_express_price(tmp_path):
    excel, db = tmp_path / "tarifa.xlsx", tmp_path / "catalog.sqlite3"
    make_excel(excel)
    from app.collectors import offers
    conn = offers.connect(db)
    old = {"quantity": 100, "kind": "total", "price": Decimal("99"), "currency": "EUR", "tax": "net", "shipping": "included", "scope": "old"}
    offers.replace_offers(conn, shop.PROVIDER, f"{shop.PAGES[0]}#1-cara-sin-acabado-7-10-dias", "viejo", [old], "2026-11-03", [])
    offers.replace_offers(conn, shop.PROVIDER, f"{shop.PAGES[1]}#barniz", "barniz", [old], "2026-11-03", [])  # another page: untouched
    conn.close()
    assert tariff.load(db, excel) == {"products": 4, "prices": 6}
    rows = sqlite3.connect(db).execute("SELECT product_url, quantity, price, tax_status, delivery_days FROM supplier_offers WHERE provider=? ORDER BY product_url, quantity", (shop.PROVIDER,)).fetchall()
    urls = {r[0] for r in rows}
    assert f"{shop.PAGES[0]}#1-cara-sin-acabado-7-10-dias" not in urls and f"{shop.PAGES[1]}#barniz" in urls
    standard = [r for r in rows if r[0].endswith("#tarifa-1-cara-sin-acabado-7-10-dias")]
    express = [r for r in rows if r[0].endswith("#tarifa-1-cara-sin-acabado-2-3-dias")]
    assert [(r[1], r[2]) for r in standard] == [(100, "30"), (250, "31")] and all(r[3] == "net" and r[4] == 10 for r in standard)
    assert [(r[1], r[2]) for r in express] == [(100, "65"), (250, "66")] and all(r[4] == 3 for r in express)  # +35 €, as the shop's configurator


def test_the_browser_reader_skips_a_page_that_has_the_tariff(tmp_path):
    from datetime import datetime, timezone
    excel, db, cache = tmp_path / "tarifa.xlsx", tmp_path / "catalog.sqlite3", tmp_path / "cache"
    make_excel(excel)
    tariff.load(db, excel)
    cache.mkdir()
    (cache / "robots.txt").write_text("User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n")
    fresh = datetime.now(timezone.utc).isoformat()
    (cache / "robots.json").write_text('{"fetched_at": "%s"}' % fresh)
    page = cache / "impresion-de-tarjetas-de-visita.html"
    page.write_text("<html></html>")
    page.with_suffix(".json").write_text('{"fetched_at": "%s"}' % fresh)
    report = shop.collect(db, cache, [shop.PAGES[0]])
    assert report["pages"][0]["status"] == "skipped"


def make_book(path, sheets):
    """An .xlsx with several sheets (columns A to M)."""
    strings = []

    def sheet_xml(rows):
        body = []
        for number, row in enumerate(rows, start=1):
            cells = []
            for column, value in zip("ABCDEFGHIJKLM", row):
                if value is None or value == "":
                    continue
                if isinstance(value, str):
                    strings.append(value)
                    cells.append(f'<c r="{column}{number}" t="s"><v>{len(strings) - 1}</v></c>')
                else:
                    cells.append(f'<c r="{column}{number}"><v>{value}</v></c>')
            body.append(f'<row r="{number}">{"".join(cells)}</row>')
        return f'<worksheet><sheetData>{"".join(body)}</sheetData></worksheet>'

    names = list(sheets)
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("xl/workbook.xml", '<workbook xmlns:r="x"><sheets>' + "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, 1)) + "</sheets></workbook>")
        book.writestr("xl/_rels/workbook.xml.rels", "<Relationships>" + "".join(f'<Relationship Id="rId{i}" Type="t" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(names) + 1)) + "</Relationships>")
        for i, name in enumerate(names, 1):
            book.writestr(f"xl/worksheets/sheet{i}.xml", sheet_xml(sheets[name]))
        book.writestr("xl/sharedStrings.xml", "<sst>" + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")


BAGS = [["UNIDADES", "MEDIDAS", "PVP PROVEEDOR", "PVP ICON", "PVP UNITARIO ICON", None, "UNIDADES", "MEDIDAS", "PVP PROVEEDOR", "PVP ICON"],
        ["Bolsas Kraft 1/0", None, None, None, None, None, "Bolsas Blancas 1/0"],
        [100, "18x8x24", 40, 90, 0.9, None, 100, "18x8x24", 42, 95],
        [250, "18x8x24", 60, 120, 0.48, None, 250, "18x8x24", "-", "-"],
        [100, "22x10x28", 45, 100, 1.0, None, 100, "22x10x28", 47, 105]]
FOLDERS = [["PRODUCTO", "unidades", "pvp proveedor", "pvp icon", None, None, None, None, None, "PRODUCTO", "unidades", "pvp proveedor", "pvp icon"],
           ["carpetas 4/0", 100, 70, 120, None, None, None, None, None, "carpetas 4/0", 100, 69, 118],
           [None, 250, 90, 150, None, None, None, None, None, None, 250, 90, 150]]
MENUS = [["UNIDADES", "MEDIDAS", "PVP PROVEEDOR", "PVP ICON", "PVP UNITARIO ICON", "PRECIO LA IMPRENTA DE INTERNET"],
         ["CARTA TRIPTICO (TRUYOL)"], [10, "21X29,7", 70, 100, 10, 92], [20, "21X29,7", 75, 115, 5.7]]


def test_other_sheets_are_read_by_their_headers(tmp_path):
    book = tmp_path / "t.xlsx"
    make_book(book, {"BOLSAS papel": BAGS, "CARPETAS": FOLDERS, "CARTAS RESTAURANTE": MENUS})
    blocks, notes = tariff.parse_tables(tariff.read_sheet(book, "BOLSAS papel"))
    assert {(b["label"], b["measure"]): b["prices"] for b in blocks} == {
        ("Bolsas Kraft 1/0", "18x8x24"): {100: Decimal("90"), 250: Decimal("120")},
        ("Bolsas Kraft 1/0", "22x10x28"): {100: Decimal("100")},
        ("Bolsas Blancas 1/0", "18x8x24"): {100: Decimal("95")},  # the "-" price is skipped
        ("Bolsas Blancas 1/0", "22x10x28"): {100: Decimal("105")}}
    assert notes == []
    blocks, notes = tariff.parse_tables(tariff.read_sheet(book, "CARPETAS"))
    assert blocks[0]["prices"] == {100: Decimal("120"), 250: Decimal("150")} and len(notes) == 1  # two tables disagree on 100 uds
    assert "120" in notes[0] and "118" in notes[0]
    sale, _ = tariff.parse_tables(tariff.read_sheet(book, "CARTAS RESTAURANTE"))
    web, _ = tariff.parse_tables(tariff.read_sheet(book, "CARTAS RESTAURANTE"), "web")
    assert sale[0]["label"] == "CARTA TRIPTICO" and sale[0]["prices"] == {10: Decimal("100"), 20: Decimal("115")}
    assert web[0]["prices"] == {10: Decimal("92")}  # the web column is only filled where the sheet has it


def test_loading_the_rest_replaces_only_its_own_products(tmp_path):
    book, db = tmp_path / "t.xlsx", tmp_path / "c.sqlite3"
    make_book(book, {"BOLSAS papel": BAGS, "TARJETAS DE VISITA": ROWS})
    assert tariff.load(db, book) == {"products": 4, "prices": 6}
    report = tariff.load_rest(db, book)
    assert report["BOLSAS papel"] == {"products": 4, "prices": 5, "precio": "icon", "notes": []} and "CAJAS" in report  # missing sheets are reported, not fatal
    count = lambda: sqlite3.connect(db).execute("SELECT count(DISTINCT product_url) FROM supplier_offers WHERE provider=?", (shop.PROVIDER,)).fetchone()[0]
    assert count() == 8
    tariff.load_rest(db, book)  # loading twice does not duplicate
    assert count() == 8
    row = sqlite3.connect(db).execute("SELECT product_name, tax_status, shipping, spec_json FROM supplier_offers WHERE product_name LIKE 'Bolsas de papel%' LIMIT 1").fetchone()
    assert row[1] == "net" and row[2] == "unknown" and "Formato" in row[3] and "Modelo" in row[3]


TABLECLOTHS = [["UNIDADES", "PVP PROVEEDOR", "PVP ICON", "PVP UNITARIO ICON"],
               ["MANTELES INDIVIDUALES (ONLINE PRINTER)", None, None, None, "pvp la imprenta", "beneficio icon"],
               [1000, 90, 140, 0.14, 138, 48], [1500, 110, 185, 0.12, 174, 64]]


def test_the_web_price_is_used_where_the_sheet_has_it_and_the_tariff_elsewhere(tmp_path):
    book, db = tmp_path / "t.xlsx", tmp_path / "c.sqlite3"
    make_book(book, {"MANTELES INDIVIDUALES": TABLECLOTHS, "BOLSAS papel": BAGS})
    web, _ = tariff.parse_tables(tariff.read_sheet(book, "MANTELES INDIVIDUALES"), "web")  # the sub-header row names the column
    assert web[0]["prices"] == {1000: Decimal("138"), 1500: Decimal("174")}
    icon, _ = tariff.parse_tables(tariff.read_sheet(book, "MANTELES INDIVIDUALES"), "icon")
    assert icon[0]["prices"] == {1000: Decimal("140"), 1500: Decimal("185")}
    report = tariff.load_rest(db, book)  # default: web price
    assert report["MANTELES INDIVIDUALES"]["precio"] == "web" and report["BOLSAS papel"]["precio"] == "icon"
    row = sqlite3.connect(db).execute("SELECT price FROM supplier_offers WHERE product_name LIKE 'Manteles%' AND quantity=1000").fetchone()
    assert row[0] == "138"


def test_a_wrong_excel_does_not_wipe_the_loaded_products(tmp_path):
    import sqlite3
    import pytest
    book, wrong, db = tmp_path / "t.xlsx", tmp_path / "w.xlsx", tmp_path / "c.sqlite3"
    make_book(book, {"BOLSAS papel": BAGS, "TARJETAS DE VISITA": ROWS})
    tariff.load_rest(db, book)
    count = lambda: sqlite3.connect(db).execute("SELECT COUNT(*) FROM supplier_offers").fetchone()[0]
    before = count()
    make_book(wrong, {"TARJETAS DE VISITA": ROWS})  # none of the "rest" sheets
    with pytest.raises(ValueError):
        tariff.load_rest(db, wrong)
    assert count() == before > 0
