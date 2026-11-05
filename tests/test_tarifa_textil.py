"""T-shirts, sweatshirts and mugs from the 2024 workbook. Invented numbers in a book shaped like the real sheets."""
from decimal import Decimal

import pytest

from app.collectors import laimprentadeinternet as shop
from app.collectors import offers, tarifa_textil as textil
from tests.test_tarifa_propia import make_book

HEAD = ["textil", "Cantidad", "Proveedor", "PVP prov.", "nuevo PVP tienda", "BENEFICIO", "PVP UNITARIO", None,
        "textil", "Cantidad", "Proveedor", "PVP prov.", "nuevo PVP tienda", "BENEFICIO", "PVP UNITARIO"]
TEXTIL = [
    HEAD,
    ["camisetas de color serigrafía 1 color parte pecho", 10, "Prov A", 60, 100, 40, 10, None, "Sudaderas capucha de color serigrafía 1 color parte pecho", 10, "Prov C", 150, 190, 40, 19],
    [None, 20, "Prov A", 100, 150, 50, 7.5, None, None, 20, "Prov C", 250, 300, 50, 15],
    [None, 50, "Prov B", 200, 275, 75, 5.5, None, None, 0, None, 0, 0, 0, 0],
    ["camisetas de color digital a color parte pecho", 10, "Prov A", 70, 110, 40, 11, None, "Gorras tipo baseball de color DTF delantera", 10, "Prov D", 40, 60, 20, 6],
    [None, 20, "Prov A", 120, 170, 50, 8.5],
    ["camisetas con error de precios", 10, "Prov A", 60, 100, 40, 10],
    [None, 20, "Prov A", 50, 90, 40, 4.5],  # the price goes DOWN when the quantity goes up: not loaded
]
MERCHAN = [
    ["Descripción", "Cantidad", "PVP Proveedor", "Nuevo PVP tienda", "pvp unitario", "beneficio"],
    ["Tazas cerámica blanca asa, MOD 1, impresas en sublimación a color", 10, 64, 104, 10.4, 40],
    [None, 20, 108, 158, 7.9, 50],
    ["Boligrafos MOD 81132, impreso tampografia 1 color", 50, 46, 86, 1.7, 40],  # the configurator of the web gives it: not loaded
    ["COMPLEMENTOS"],
    ["ARTES FINALES (+15,00€)"],
]


@pytest.fixture
def book(tmp_path):
    path = tmp_path / "precios.xlsx"
    make_book(path, {"TEXTIL": TEXTIL, "MERCHAN okok": MERCHAN, "Flyers okok": [["x"]]})
    return path


def test_blocks_are_read_from_both_tables_of_the_sheet_side_by_side(book):
    blocks = textil.blocks_of(shop_rows(book, "TEXTIL"), textil.TEXTIL_SIDES)
    labels = [b["label"] for b in blocks]
    assert labels[0] == "camisetas de color serigrafía 1 color parte pecho" and "Sudaderas capucha de color serigrafía 1 color parte pecho" in labels
    first = blocks[0]
    assert [(r["quantity"], r["cost"], r["price"], r["supplier"]) for r in first["rows"]] == [
        (10, Decimal("60"), Decimal("100"), "Prov A"), (20, Decimal("100"), Decimal("150"), "Prov A"), (50, Decimal("200"), Decimal("275"), "Prov B")]
    sweatshirts = next(b for b in blocks if b["label"].startswith("Sudaderas"))
    assert [r["quantity"] for r in sweatshirts["rows"]] == [10, 20]  # the row with quantity 0 and price 0 is skipped


def shop_rows(book, sheet):
    from app.collectors.tarifa_propia import read_sheet
    return read_sheet(book, sheet)


def test_only_what_the_web_cannot_read_is_loaded_with_price_cost_and_the_page_of_the_shop(book, tmp_path):
    db = tmp_path / "c.sqlite3"
    report = textil.load(db, book)
    assert report["products"] == 4  # 2 T-shirt blocks (the incoherent one is out), 1 sweatshirt, 1 mug
    assert report["pages"] == sorted([f"{shop.SITE}/impresion-de-camisetas/", f"{shop.SITE}/sudaderas-personalizadas/", f"{shop.SITE}/tazas/"])
    notes = " | ".join(report["notes"])
    assert "Gorras" in notes and "Boligrafos" in notes  # their own configurators give the real price
    assert "el precio baja al subir la cantidad" in notes  # an incoherent block is not loaded, and it says why
    conn = offers.connect(db)
    rows = conn.execute("SELECT product_url, quantity, price, tax_status, shipping, scope FROM supplier_offers WHERE provider=? ORDER BY product_url, quantity", (shop.PROVIDER,)).fetchall()
    assert all("#tarifa-textil-" in r[0] and r[3] == "net" and r[4] == "unknown" and "sin confirmar en la web" in r[5] for r in rows)
    assert {r[0].split("#")[0] for r in rows} == {f"{shop.SITE}/impresion-de-camisetas/", f"{shop.SITE}/sudaderas-personalizadas/", f"{shop.SITE}/tazas/"}
    pecho = [r for r in rows if "serigrafia-1-color-parte-pecho" in r[0] and "camisetas" in r[0]]
    assert [(r[1], Decimal(r[2])) for r in pecho] == [(10, Decimal("100")), (20, Decimal("150")), (50, Decimal("275"))]  # "nuevo PVP tienda", not the cost
    costs = dict(conn.execute("SELECT quantity, cost FROM own_costs WHERE product_url LIKE '%camisetas%serigrafia-1-color-parte-pecho'").fetchall())
    assert {q: Decimal(c) for q, c in costs.items()} == {10: Decimal("60"), 20: Decimal("100"), 50: Decimal("200")}  # the margin shows on the card
    conn.close()


def test_a_second_load_replaces_the_first_and_does_not_touch_other_prices(book, tmp_path):
    db = tmp_path / "c.sqlite3"
    conn = offers.connect(db)
    row = {"quantity": 1, "kind": "total", "price": "9", "currency": "EUR", "tax": "net", "shipping": "included", "scope": "t"}
    offers.replace_offers(conn, shop.PROVIDER, f"{shop.SITE}/otra/#config", "Otra", [row], "2026-11-05")
    conn.close()
    textil.load(db, book)
    textil.load(db, book)
    conn = offers.connect(db)
    assert conn.execute("SELECT count(DISTINCT product_url) FROM supplier_offers WHERE product_url LIKE '%#tarifa-textil-%'").fetchone()[0] == 4
    assert conn.execute("SELECT count(*) FROM supplier_offers WHERE product_url LIKE '%#tarifa-textil-%'").fetchone()[0] == 3 + 2 + 2 + 2  # loaded twice, stored once
    assert conn.execute("SELECT count(*) FROM supplier_offers WHERE product_url=?", (f"{shop.SITE}/otra/#config",)).fetchone()[0] == 1  # untouched
    conn.close()


def test_a_wrong_excel_changes_nothing(tmp_path):
    path = tmp_path / "otro.xlsx"
    make_book(path, {"TEXTIL": [HEAD], "MERCHAN okok": [MERCHAN[0]]})
    with pytest.raises(ValueError, match="no cambio nada"):
        textil.load(tmp_path / "c.sqlite3", path)


def test_the_specification_names_garment_technique_and_zone():
    spec = {(x["group"], x["label"]) for x in textil.spec_of("camisetas de color serigrafía 1 color delantera o trasera (max 30x30 cm)", "textil")}
    assert ("Prenda", "Camisetas de color") in spec and ("Impresión", "serigrafía 1 color") in spec
    assert ("Zona de impresión", "delantera o trasera (max 30x30 cm)") in spec


def test_the_cli_picks_the_sheets_by_the_book_it_is_given(book, tmp_path):
    from app.collectors import tarifa_propia as tariff
    assert [n for n in tariff.sheet_names(book)] == ["TEXTIL", "MERCHAN okok", "Flyers okok"]
