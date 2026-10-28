import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers.price_matrix import MatrixError, es_money, parse_matrix
from app.parsers.product_page import default_configuration
from app.services.importer import connect, import_matrix

REAL = json.loads((Path(__file__).parent / "fixtures/flyers_calculation_data.real.json").read_text(encoding="utf-8"))
WHEN = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
URL = "https://print24.com/es/productos-impresion/flyers"


def page(data=REAL, noise=True):
    """Wrap data the way Next.js ships it: JSON inside an escaped string inside a push call."""
    chunk = '1:{"calculationData":' + json.dumps(data) + "}"
    half = len(chunk) // 2  # fragments must be joined before parsing
    pushes = [chunk[:half], chunk[half:]]
    html = "".join(f"<script>self.__next_f.push([1,{json.dumps(p)}])</script>" for p in pushes)
    return ("<html>" + ('<script>self.__next_f.push([0])</script>' if noise else "") + html + "</html>")


def test_es_money():
    assert es_money("4,92 €") == Decimal("4.92")
    assert es_money("1.234,56\xa0€") == Decimal("1234.56")
    for bad in ("4.92", "4,9 €", "abc", None, 4.92):
        with pytest.raises(MatrixError):
            es_money(bad)


def test_real_matrix_parses_with_exact_values():
    matrix, _ = default_configuration(page(), url=URL, observed_at=WHEN)
    offers = parse_matrix(matrix)
    assert len(offers) == 6  # 2 quantities x 3 shipping types
    first = offers[0]
    assert (first.quantity_id, first.quantity_value, first.delivery_type) == ("400", 100, "standard")
    assert (first.product_net, first.shipping_net, first.total_net, first.total_vat, first.total_gross) == (
        Decimal("11.13"), Decimal("4.92"), Decimal("16.05"), Decimal("3.37"), Decimal("19.42"))
    assert first.delivery_text.startswith("Entrega hasta")


def test_context_excludes_spanned_groups_and_marks_scope():
    _, context = default_configuration(page(), url=URL, observed_at=WHEN)
    names = {p["name"] for p in context["properties"]}
    assert not names & {"quantity", "shipping_type"}
    assert {"format": "222"}.items() <= {p["name"]: p["id"] for p in context["properties"]}.items()
    assert context["product_id"] == "63" and context["country"] == "ES" and context["currency"] == "EUR"
    assert context["account_scope"] == "public-web-no-session"
    assert context["valid_until"] > context["observed_at"]


def test_import_into_database_is_repeatable(tmp_path):
    matrix, context = default_configuration(page(), url=URL, observed_at=WHEN)
    db = connect(tmp_path / "t.sqlite3")
    cid = import_matrix(db, matrix, context, source=URL)
    assert import_matrix(db, matrix, context, source=URL) == cid
    assert db.execute("SELECT count(*) FROM prices").fetchone()[0] == 6
    assert db.execute("SELECT count(*) FROM price_history").fetchone()[0] == 0
    assert db.execute("SELECT total_net FROM prices WHERE delivery_days='5' AND quantity_id=1").fetchone()[0] == "16.05"
    db.close()


def test_inconsistent_shipping_is_rejected():
    broken = json.loads(json.dumps(REAL))
    final = broken["priceMatrix"][0]["quantity"]["shipping_type"][0]["price"]["final_prices"]
    final["shipping_net"] = "9,99 €"
    matrix, _ = default_configuration(page(broken), url=URL, observed_at=WHEN)
    with pytest.raises(MatrixError, match="shipping_net"):
        parse_matrix(matrix)


def test_page_without_data_or_matrix():
    with pytest.raises(MatrixError):
        default_configuration("<html></html>", url=URL, observed_at=WHEN)
    no_matrix = {"itemMaster": REAL["itemMaster"]}
    with pytest.raises(MatrixError):
        default_configuration(page(no_matrix), url=URL, observed_at=WHEN)


def test_default_spec_labels():
    from app.collectors.specs import default_spec
    data = {"itemMaster": {"selectedProps": [{"id": "222", "name": "format"}, {"id": "400", "name": "quantity"}, {"id": "9", "name": "hid"}],
        "boxes": [
            {"propGroupName": "format", "boxTitleTranslated": "Formato", "hide": 0,
             "properties": [{"pgrId": "1", "propertyTranslated": ["x"]}, {"pgrId": "222", "propertyTranslated": ["105 x", "148 mm", "DIN A6"]}]},
            {"propGroupName": "quantity", "boxTitleTranslated": "Cantidad", "hide": 0, "properties": [{"pgrId": "400", "propertyTranslated": ["100"]}]},
            {"propGroupName": "hid", "boxTitleTranslated": "H", "hide": 1, "properties": [{"pgrId": "9", "propertyTranslated": ["oculto"]}]}]}}
    assert default_spec(data) == [{"group": "Formato", "label": "105 x 148 mm DIN A6"}]
