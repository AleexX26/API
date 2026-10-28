import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.collectors import products, sitemaps

REAL = json.loads((Path(__file__).parent / "fixtures/flyers_calculation_data.real.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
U1, U2, U3 = (f"https://print24.com/es/productos-impresion/{n}" for n in ("flyers", "roto", "otro"))
ROBOTS = "User-agent: *\nAllow: /es\nDisallow: /es-\n"


def html_for(data):
    chunk = '1:{"calculationData":' + json.dumps(data) + "}"
    return f'<html><script>self.__next_f.push([1,{json.dumps(chunk)}])</script></html>'


@pytest.fixture
def setup(tmp_path, monkeypatch):
    robots = tmp_path / "robots.txt"
    robots.write_text(ROBOTS)
    pages = {U1: html_for(REAL), U2: "<html>sin datos</html>", U3: html_for(REAL)}
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


def test_collect_imports_skips_unparseable_and_caches(setup):
    tmp, robots, pages, calls = setup
    db = tmp / "c.sqlite3"
    first = products.collect(db, [U1, U2], tmp / "cache", robots, NOW)
    assert [p["status"] for p in first["pages"]] == ["ok", "failed"]
    assert first["pages"][0]["prices"] == 6 and first["pages"][0]["product_id"] == "63"
    assert first["network_requests"] == 2
    again = products.collect(db, [U1, U2], tmp / "cache", robots, NOW)
    assert again["network_requests"] == 0 and len(calls) == 2
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM prices").fetchone()[0] == 6
        assert conn.execute("SELECT status FROM product_pages ORDER BY url").fetchall() == [("ok",), ("failed",)]


def test_challenge_stops_whole_run(setup):
    tmp, robots, pages, calls = setup
    pages[U2] = "<html>Please verify you are human</html>"
    with pytest.raises(ValueError, match="challenge"):
        products.collect(tmp / "c.sqlite3", [U1, U2, U3], tmp / "cache", robots, NOW)
    assert U3 not in calls


def test_robots_block_makes_no_request(setup):
    tmp, robots, pages, calls = setup
    robots.write_text("User-agent: *\nDisallow: /es/productos-impresion")
    with pytest.raises(ValueError, match="robots"):
        products.collect(tmp / "c.sqlite3", [U1], tmp / "cache", robots, NOW)
    assert not calls


def test_cache_name_and_product_urls(tmp_path):
    assert products.cache_name(U1) == "productos-impresion__flyers.html"
    db = tmp_path / "u.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE catalog_urls (url TEXT, kind TEXT)")
        conn.executemany("INSERT INTO catalog_urls VALUES (?,?)", [(U3, "product"), (U1, "product"), (U2, "category")])
    assert products.product_urls(db) == [U1, U3]
    assert products.product_urls(db, 1) == [U1]
