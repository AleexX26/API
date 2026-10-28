import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.collectors import variants
from app.parsers.price_matrix import MatrixError
from app.services.importer import connect

REAL = json.loads((Path(__file__).parent / "fixtures/flyers_calculation_data.real.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def data(boxes=None):
    d = json.loads(json.dumps(REAL))
    d["itemMaster"]["boxes"] = boxes if boxes is not None else [
        {"propGroupName": "papier", "boxTitleTranslated": "Papel", "hide": 0, "properties": [
            {"pgrId": "3783", "propertyTranslated": ["115 g/m²", "Papel estucado"]},
            {"pgrId": "4109", "propertyTranslated": ["135 g/m²", "Papel estucado"]},
            {"pgrId": "3796", "propertyTranslated": ["170 g/m²", "Papel estucado"]}]},
        {"propGroupName": "format", "boxTitleTranslated": "Formato", "hide": 0, "properties": [
            {"pgrId": "222", "propertyTranslated": ["105 x 148 mm", "DIN A6"]},
            {"pgrId": "0", "propertyTranslated": ["Elija el formato personalizado"]},
            {"pgrId": "207", "propertyTranslated": ["74 x 105 mm", "DIN A7"]}]},
        {"propGroupName": "quantity", "boxTitleTranslated": "Cantidad", "hide": 0, "properties": [
            {"pgrId": "400", "propertyTranslated": ["100"]}, {"pgrId": "378", "propertyTranslated": ["125"]}]},
        {"propGroupName": "quality", "boxTitleTranslated": "", "hide": 1, "properties": [
            {"pgrId": "4560", "propertyTranslated": ["normal"]}, {"pgrId": "9332", "propertyTranslated": ["green"]}]}]
    return d


def test_variations_change_one_option_and_skip_default_hidden_and_spanned():
    found = variants.variations(data())
    assert [(v["group"], v["option_id"], v["label"]) for v in found] == [
        ("papier", "4109", "135 g/m² Papel estucado"), ("papier", "3796", "170 g/m² Papel estucado"), ("format", "207", "74 x 105 mm DIN A7")]


def test_build_payload_matches_the_pages_own_request():
    d = data()
    base = variants.build_payload(d)
    assert base["product_alias_id"] == 63 and base["delivery_country_code"] == "ES" and base["premium_file_check"] == 0
    assert base["quantities"] == [row["quantity"]["id"] for row in d["priceMatrix"]]
    names = [p["name"] for p in base["properties"]]
    assert "quantity" not in names and "shipping_type" not in names and names.count("format") == 1
    changed = variants.build_payload(d, {"group": "format", "option_id": "207"})
    diff = [(a, b) for a, b in zip(base["properties"], changed["properties"]) if a != b]
    assert diff == [({"id": "222", "name": "format"}, {"id": "207", "name": "format"})]  # exactly one property differs


def test_store_variant_imports_prices_and_readable_spec(tmp_path):
    d = data()
    text = json.dumps(d["priceMatrix"])
    change = {"group": "papier", "title": "Papel", "option_id": "4109", "label": "135 g/m² Papel estucado"}
    db = connect(tmp_path / "c.sqlite3")
    db.executescript(variants.SCHEMA)
    cid = variants.store_variant(db, "https://print24.com/es/productos-impresion/flyers", d, change, text, NOW)
    assert db.execute("SELECT count(*) FROM prices WHERE configuration_id=?", (cid,)).fetchone()[0] == 6
    title, spec = db.execute("SELECT title, spec_json FROM config_specs WHERE configuration_id=?", (cid,)).fetchone()
    assert title == "Papel: 135 g/m² Papel estucado"
    canonical = json.loads(db.execute("SELECT canonical_json FROM configurations WHERE id=?", (cid,)).fetchone()[0])
    assert {"id": "4109", "name": "papier"} in canonical["properties"] and canonical["product_id"] == "63"
    again = variants.store_variant(db, "https://print24.com/es/productos-impresion/flyers", d, change, text, NOW)
    assert again == cid and db.execute("SELECT count(*) FROM prices").fetchone()[0] == 6  # repeating does not duplicate


def test_store_variant_rejects_an_empty_answer(tmp_path):
    db = connect(tmp_path / "c.sqlite3")
    db.executescript(variants.SCHEMA)
    with pytest.raises(MatrixError):
        variants.store_variant(db, "u", data(), {"group": "papier", "title": "Papel", "option_id": "4109", "label": "x"}, "", NOW)
    assert db.execute("SELECT count(*) FROM prices").fetchone()[0] == 0
