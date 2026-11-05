"""The REAL capture the owner copied from DevTools lives in data/capturas/ (outside git). This test only checks invariants of it,
never its figures, so no real price is written in the repository; it is skipped when the file is not on this PC."""
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers.price_matrix import parse_matrix
from app.services import print24_captures as caps

FOLDER = Path(__file__).resolve().parents[1] / "data" / "capturas"
FILES = sorted(FOLDER.glob("*.response.json"))
pytestmark = pytest.mark.skipif(not FILES, reason="no hay capturas reales en data/capturas")


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_a_real_capture_fits_the_parser_and_is_internally_consistent(path):
    prices = parse_matrix(path.read_text(encoding="utf-8"))
    assert prices
    for p in prices:
        assert p.total_net == p.product_net + p.shipping_net
        assert abs(p.total_net + p.total_vat - p.total_gross) <= Decimal("0.01")
    by_quantity = {}
    for p in prices:
        by_quantity.setdefault(p.quantity_value, {})[p.delivery_type] = p
    for quantity, kinds in by_quantity.items():
        assert {"standard", "express", "priority"} <= set(kinds), quantity
        assert kinds["standard"].total_net <= kinds["express"].total_net <= kinds["priority"].total_net  # faster costs more
        assert int(kinds["standard"].delivery_days) >= int(kinds["express"].delivery_days) >= int(kinds["priority"].delivery_days)
    assert list(by_quantity) == sorted(by_quantity)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_a_real_capture_imports_into_a_temporary_database(path, tmp_path):
    config = {"format": "formato de prueba", "paper": "papel de prueba", "sides": "1 cara", "finishing": "Sin Acabados"}
    text = path.read_text(encoding="utf-8")
    result = caps.import_capture(tmp_path / "catalog.sqlite3", text, config)
    assert result["prices"] == len(parse_matrix(text))
    stored = caps.list_captures(tmp_path / "catalog.sqlite3")
    assert sum(len(i["rows"]) for i in stored) == result["prices"]
