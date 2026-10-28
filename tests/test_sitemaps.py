import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.collectors import sitemaps
from app.collectors.sitemaps import collect, parse_urlset

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
ROBOTS = "User-agent: *\nAllow: /es\nDisallow: /es-\n"


def urlset(*entries):
    body = "".join(f"<url><loc>{u}</loc>" + (f"<lastmod>{m}</lastmod>" if m else "") + "</url>" for u, m in entries)
    return f"<urlset {NS}>{body}</urlset>".encode()


def test_parse_scope_dedup_and_total():
    raw = urlset(("https://print24.com/es/a", "2026-01-01"), ("https://print24.com/es/a", None),
                 ("https://print24.com/es/b?x=1", None), ("https://evil.test/es/c", None))
    urls, total = parse_urlset(raw)
    assert urls == [("https://print24.com/es/a", "2026-01-01")]
    assert total == 4


def test_parse_rejects_non_urlset():
    with pytest.raises(ValueError):
        parse_urlset(f"<sitemapindex {NS}/>".encode())
    with pytest.raises(ValueError):
        parse_urlset(b"<html/>")


@pytest.fixture
def fake_network(monkeypatch):
    calls = []

    def fake_fetch(url, cache_file, now, state, max_age_days=30):
        meta = cache_file.with_suffix(".json")
        if cache_file.exists() and meta.exists():
            return cache_file.read_bytes(), True
        calls.append(url)
        state["requests"] = state.get("requests", 0) + 1
        raw = urlset((url.replace(".xml", "/uno"), "2026-10-01"), (url.replace(".xml", "/dos"), None))
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(raw)
        meta.write_text("{}")
        return raw, False

    monkeypatch.setattr(sitemaps, "fetch_cached", fake_fetch)
    return calls


def test_collect_stores_urls_and_reuses_cache(tmp_path, fake_network):
    robots = tmp_path / "robots.txt"
    robots.write_text(ROBOTS)
    maps = {"category": "https://print24.com/es/sitemap_category.xml", "product": "https://print24.com/es/sitemap_product.xml"}
    db = tmp_path / "c.sqlite3"
    first = collect(db, tmp_path / "cache", robots, maps)
    assert first["network_requests"] == 2
    second = collect(db, tmp_path / "cache", robots, maps)
    assert second["network_requests"] == 0
    assert len(fake_network) == 2
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM catalog_urls").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM sitemap_fetches").fetchone()[0] == 2


def test_collect_blocked_by_robots_makes_no_request(tmp_path, fake_network):
    robots = tmp_path / "robots.txt"
    robots.write_text("User-agent: *\nDisallow: /es/sitemap")
    with pytest.raises(ValueError):
        collect(tmp_path / "c.sqlite3", tmp_path / "cache", robots, {"product": "https://print24.com/es/sitemap_product.xml"})
    assert not fake_network
    assert not (tmp_path / "c.sqlite3").exists()


def test_cache_expiry_and_pause(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(sitemaps.time, "sleep", sleeps.append)

    class Resp:
        status = 200
        headers = {"Content-Type": "application/xml"}
        def read(self, n): return urlset(("https://print24.com/es/x", None))
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class Opener:
        def open(self, req, timeout): return Resp()

    monkeypatch.setattr(sitemaps, "build_opener", lambda *a: Opener())
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    state = {}
    sitemaps.fetch_cached("https://print24.com/es/a.xml", tmp_path / "a.xml", now, state)
    sitemaps.fetch_cached("https://print24.com/es/b.xml", tmp_path / "b.xml", now, state)
    assert sleeps == [sitemaps.PAUSE]  # pause only between the two real requests
    _, cached = sitemaps.fetch_cached("https://print24.com/es/a.xml", tmp_path / "a.xml", now + timedelta(days=1), state)
    assert cached and state["requests"] == 2
    _, cached = sitemaps.fetch_cached("https://print24.com/es/a.xml", tmp_path / "a.xml", now + timedelta(days=31), state)
    assert not cached and state["requests"] == 3
