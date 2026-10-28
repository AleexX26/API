import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers.price_matrix import MatrixError, amount, parse_matrix
from app.services.importer import canonical_context, connect, import_matrix

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def raw():
    return (FIXTURES / "price_matrix.synthetic.json").read_text()


@pytest.fixture
def context():
    return json.loads((FIXTURES / "context.synthetic.json").read_text())


@pytest.fixture
def db(tmp_path):
    connection = connect(tmp_path / "test.sqlite3")
    yield connection
    connection.close()


def test_decimal_and_quantity(raw):
    offer = parse_matrix(raw)[0]
    assert offer.product_net == Decimal("100.10")
    assert offer.unit_product_net == Decimal("1.001")
    assert offer.shipping_gross is None
    assert offer.quantity_id != str(offer.quantity_value)
    assert parse_matrix(raw.replace('"100.10"', '100.10'))[0].product_net == Decimal("100.10")


@pytest.mark.parametrize("value", [True, 0.1, "NaN", "Infinity", "-1", "1,20", None])
def test_bad_money(value):
    with pytest.raises(MatrixError):
        amount(value)


@pytest.mark.parametrize("raw", ['[]', '{}', '0', 'null', '[{}]', 'not json', '[NaN]'])
def test_bad_envelope(raw):
    with pytest.raises(MatrixError):
        parse_matrix(raw)


def test_invalid_quantity_vat_and_duplicate(raw):
    for changed in (raw.replace('100,', '0,'), raw.replace('133.22', '200.00')):
        with pytest.raises(MatrixError):
            parse_matrix(changed)
    rows = json.loads(raw)
    with pytest.raises(MatrixError):
        parse_matrix(json.dumps(rows + rows))


def test_configuration_identity(context):
    context["properties"].append({"name": "paper", "id": "other"})
    first = canonical_context(context)
    context["properties"].reverse()
    assert first == canonical_context(context)
    context["services"]["premium_file_check"] = 1
    assert first != canonical_context(context)


def test_import_monthly_history_and_failed_update(db, raw, context):
    cid = import_matrix(db, raw, context, source="synthetic")
    assert db.execute("SELECT count(*) FROM configuration_options").fetchone()[0] == 1
    assert import_matrix(db, raw, context, source="retry") == cid
    assert db.execute("SELECT count(*) FROM price_history").fetchone()[0] == 0
    context.update(observed_at="2026-11-01T00:00:00Z", valid_until="2026-12-01T00:00:00Z")
    updated = raw.replace("100.10", "101.10").replace("110.10", "111.10").replace("133.22", "134.22")
    import_matrix(db, updated, context, source="monthly simulation")
    assert db.execute("SELECT product_net FROM prices").fetchone()[0] == "101.10"
    old = json.loads(db.execute("SELECT old_snapshot_json FROM price_history").fetchone()[0])
    assert old["product_net"] == "100.10"
    with pytest.raises(MatrixError):
        import_matrix(db, "[{}]", context, source="broken")
    assert db.execute("SELECT product_net FROM prices").fetchone()[0] == "101.10"
    assert db.execute("SELECT status FROM sync_runs ORDER BY id DESC").fetchone()[0] == "failed"
    assert db.execute("SELECT count(*) FROM sync_errors").fetchone()[0] == 1


def test_stale_observation_rolls_back(db, raw, context):
    import_matrix(db, raw, context, source="initial")
    context["observed_at"] = "2026-09-01T00:00:00Z"
    with pytest.raises(ValueError, match="older"):
        import_matrix(db, raw, context, source="stale")
    assert db.execute("SELECT count(*) FROM price_history").fetchone()[0] == 0
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_failure_after_first_write_rolls_back_entire_batch(db, raw, context):
    import_matrix(db, raw, context, source="initial")
    rows = json.loads(raw)
    extra = json.loads(raw)[0]
    extra["quantity"]["id"] = "new-quantity"
    context["observed_at"] = "2026-09-01T00:00:00Z"
    with pytest.raises(ValueError, match="older"):
        import_matrix(db, json.dumps([extra, *rows]), context, source="partial failure")
    assert db.execute("SELECT count(*) FROM prices").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM quantities").fetchone()[0] == 1


def test_cli_roundtrip(tmp_path):
    import csv
    import subprocess
    import sys
    base = [sys.executable, "main.py", "--db", str(tmp_path / "cli.sqlite3")]
    def run(*args):
        return subprocess.run([*base, *map(str, args)], check=True, capture_output=True, text=True)
    run("init-db")
    run("import-matrix", FIXTURES / "price_matrix.synthetic.json", FIXTURES / "context.synthetic.json")
    assert json.loads(run("status").stdout)["prices"] == 1
    run("export", tmp_path / "export.json")
    run("export", tmp_path / "export.csv", "--format", "csv")
    exported = json.loads((tmp_path / "export.json").read_text())
    assert exported[0]["product_net"] == "100.10"
    assert exported[0]["currency"] == "EUR"
    with (tmp_path / "export.csv").open(newline="", encoding="utf-8") as handle:
        assert list(csv.DictReader(handle))[0]["quantity_value"] == "100"
