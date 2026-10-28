import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.collectors import sitemaps, tuskamisetas
from app.parsers.price_matrix import MatrixError

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
ROBOTS = "User-agent: *\nDisallow: /*/busca/\nDisallow: /*?filtros=\n"
URL = "https://www.tuskamisetas.com/es/producto/b-c-e150-t-shirt"
BAD = "https://www.tuskamisetas.com/es/producto/roto"


def page(low="1.41", high="3.15", rows=None, name="Camiseta #E150", qty=("1000", "500", "1")):
    ld = {"@context": "https://schema.org", "@type": "Product", "name": name,
          "offers": {"@type": "AggregateOffer", "priceCurrency": "EUR", "lowPrice": low, "highPrice": high}}
    rows = rows or [("Blanco", ["1,41 €", "1,53 €", "2,75 €"]), ("Color", ["1,62 €", "1,75 €", "3,15 €"])]
    head = "".join(f"<td>{q}</td>" for q in qty)
    body = "".join("<tr><td>" + label + "</td>" + "".join(f"<td>\n {p} </td>" for p in prices) + "</tr>" for label, prices in rows)
    return (f'<html><script type="application/ld+json">{json.dumps(ld)}</script>'
            '<table><tr><td>Talla</td><td>Medidas</td></tr><tr><td>XS</td><td>40</td></tr></table>'
            f'<table><tr><td><b>Adulto</b></td>{head}</tr>{body}</table></html>')


def test_parse_tiers_exact_and_ignores_size_chart():
    result = tuskamisetas.parse_page(page())
    assert result["name"] == "Camiseta #E150" and result["currency"] == "EUR"
    assert len(result["tiers"]) == 6
    first = result["tiers"][0]
    assert (first["group"], first["variant"], first["min_quantity"], first["unit_price"]) == ("Adulto", "Blanco", 1000, Decimal("1.41"))
    assert result["tiers"][-1]["unit_price"] == Decimal("3.15")


def test_parse_rejects_inconsistent_or_missing_data():
    with pytest.raises(MatrixError, match="lowPrice"):
        tuskamisetas.parse_page(page(low="1.00"))
    with pytest.raises(MatrixError, match="highPrice"):
        tuskamisetas.parse_page(page(high="9.99"))
    with pytest.raises(MatrixError, match="No price"):
        tuskamisetas.parse_page(page().split("<table>")[0] + "</html>")
    with pytest.raises(MatrixError, match="Product"):
        tuskamisetas.parse_page("<html><table><tr><td>Adulto</td><td>1</td></tr></table></html>")
    with pytest.raises(MatrixError):
        tuskamisetas.parse_page(page(rows=[("Blanco", ["1,41 €", "1,53 €"])]))
    with pytest.raises(MatrixError):
        tuskamisetas.parse_page(page(rows=[("Blanco", ["1.41", "1,53 €", "3,15 €"])]))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    robots = tmp_path / "robots.txt"
    robots.write_text(ROBOTS)
    pages = {URL: page(), BAD: "<html>nada</html>"}
    calls = []

    def fake(url, cache_file, now, state, max_age_days=30, expected="xml"):
        meta = cache_file.with_suffix(".json")
        if cache_file.exists() and meta.exists():
            return cache_file.read_bytes(), True
        calls.append(url)
        state["requests"] = state.get("requests", 0) + 1
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(pages[url], encoding="utf-8")
        meta.write_text(json.dumps({"fetched_at": now.isoformat()}))
        return cache_file.read_bytes(), False

    monkeypatch.setattr(sitemaps, "fetch_cached", fake)
    return tmp_path, robots, pages, calls


def test_collect_stores_tiers_skips_bad_page_and_caches(setup):
    tmp, robots, pages, calls = setup
    db = tmp / "c.sqlite3"
    first = tuskamisetas.collect(db, [URL, BAD], tmp / "cache", robots, NOW)
    assert [p["status"] for p in first["pages"]] == ["ok", "failed"]
    assert first["network_requests"] == 2
    assert tuskamisetas.collect(db, [URL, BAD], tmp / "cache", robots, NOW)["network_requests"] == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM supplier_offers").fetchone()[0] == 6
        assert conn.execute("SELECT DISTINCT tax_status FROM supplier_offers").fetchall() == [("unknown",)]
        assert conn.execute("SELECT price FROM supplier_offers WHERE variant='Color' AND quantity=1").fetchone()[0] == "3.15"
        assert conn.execute("SELECT status FROM supplier_pages ORDER BY url").fetchall() == [("ok",), ("failed",)]


def test_recollect_replaces_old_prices(setup):
    tmp, robots, pages, calls = setup
    db = tmp / "c.sqlite3"
    tuskamisetas.collect(db, [URL], tmp / "cache", robots, NOW)
    pages[URL] = page(low="1.50", rows=[("Blanco", ["1,50 €", "1,60 €", "2,80 €"]), ("Color", ["1,62 €", "1,75 €", "3,15 €"])])
    later = datetime(2026, 12, 1, tzinfo=timezone.utc)
    tuskamisetas.collect(db, [URL], tmp / "cache", robots, later)  # cache expired -> fetch fake ignores age; clear it
    # the fake serves cached pages regardless of age, so emulate expiry by removing the cache
    for f in (tmp / "cache").glob("*"):
        f.unlink()
    tuskamisetas.collect(db, [URL], tmp / "cache", robots, later)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM supplier_offers").fetchone()[0] == 6
        assert conn.execute("SELECT price FROM supplier_offers WHERE variant='Blanco' AND quantity=1000").fetchone()[0] == "1.50"


def test_robots_block_and_challenge(setup):
    tmp, robots, pages, calls = setup
    with pytest.raises(ValueError, match="robots"):
        tuskamisetas.collect(tmp / "c.sqlite3", ["https://www.tuskamisetas.com/es/busca/camiseta"], tmp / "cache", robots, NOW)
    assert not calls
    pages[BAD] = "<html>Just a moment...</html>"
    with pytest.raises(ValueError, match="challenge"):
        tuskamisetas.collect(tmp / "c.sqlite3", [BAD, URL], tmp / "cache", robots, NOW)
    assert URL not in calls


def test_repeated_column_same_price_is_merged_but_conflict_rejected():
    qty = ("1000", "500", "1", "1")
    rows = [("Blanco", ["1,41 €", "1,53 €", "2,75 €", "2,75 €"]), ("Color", ["1,62 €", "1,75 €", "3,15 €", "3,15 €"])]
    result = tuskamisetas.parse_page(page(rows=rows, qty=qty))
    assert len(result["tiers"]) == 6 and result["duplicate_columns"] == 2
    rows[0][1][3] = "2,80 €"
    with pytest.raises(MatrixError, match="Conflicting"):
        tuskamisetas.parse_page(page(rows=rows, qty=qty, high="3.15"))


def test_plus_prefixed_quantity_headers():
    result = tuskamisetas.parse_page(page(qty=("+1000", "+500", "+1")))
    assert [t["min_quantity"] for t in result["tiers"][:3]] == [1000, 500, 1]


def test_three_decimal_unit_prices_are_kept_exactly():
    rows = [("Blanco", ["0,340 €", "0,368 €", "0,66 €"]), ("Color", ["0,340 €", "0,368 €", "0,663 €"])]
    result = tuskamisetas.parse_page(page(low="0.34", high="0.66", rows=rows))
    assert result["tiers"][0]["unit_price"] == Decimal("0.340") and str(result["tiers"][-1]["unit_price"]) == "0.663"
    assert tuskamisetas.unit_price("1.234,50 €") == Decimal("1234.50")
    for bad in ("1,5 €", "1,23456 €", "1.23 €", "abc"):
        with pytest.raises(MatrixError):
            tuskamisetas.unit_price(bad)
