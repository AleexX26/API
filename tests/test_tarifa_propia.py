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
