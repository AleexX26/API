import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.collectors import offers, onlineprinters, printai, sitemaps
from app.parsers.price_matrix import MatrixError

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def op_page(active_price="42,80", base="42,80", gross="51,79", tiles=(("25", "31,66", False), ("1.000", "42,80", True)), title="Imprimir flyers A5 | Onlineprinters"):
    tile = "".join(
        f'<label class="productConfigTile {"active" if on else ""}" data-x=""><div class="inner"><div class="opidProductConfigTileLabel1">{q}</div>'
        f'<div class="price">&euro; {p}</div></div></label>' for q, p, on in tiles)
    return (f"<html><head><title>{title}</title></head><body>"
            '<dl><dt class="productConfigItemHeadTitle">Formato</dt><dd class="x">A5 (14,8 x 21,0 cm)</dd></dl>'
            '<dl><dt class="productConfigItemHeadTitle">Cantidad</dt><dd>1.000</dd></dl>'
            '<dl><dt class="productConfigItemHeadTitle">Papel</dt><dd>130 g/m&sup2; papel cuch&eacute;</dd></dl>'
            f"{tile}<div>Precio base (sin IVA)<span>&euro; <b>{base}</b></span></div>"
            f"<div>incl. 21% IVA <span>&euro; {gross}</span></div></body></html>")


def test_onlineprinters_parses_tiles_spec_and_checks_totals():
    result = onlineprinters.parse_page(op_page())
    assert result["name"] == "Imprimir flyers A5" and result["default_quantity"] == 1000
    assert result["tiers"] == [(25, Decimal("31.66")), (1000, Decimal("42.80"))]
    assert [s["group"] for s in result["spec"]] == ["Formato", "Papel"]  # quantity is the variable, not the spec
    assert result["spec"][1]["label"] == "130 g/m² papel cuché"


@pytest.mark.parametrize("changes,message", [
    ({"base": "40,00"}, "base price"),
    ({"gross": "60,00"}, "Gross"),
    ({"tiles": ()}, "No quantity"),
    ({"tiles": (("25", "1,00", False), ("25", "2,00", False), ("1.000", "42,80", True))}, "Conflicting"),
])
def test_onlineprinters_rejects_inconsistent_pages(changes, message):
    with pytest.raises(MatrixError, match=message):
        onlineprinters.parse_page(op_page(**changes))


def pa_page(net="31.24", tax="6.5604", gross="37.8", ld_price="37.80", qty_select=True):
    ld = {"@type": "Product", "name": "Flyers", "offers": {"priceCurrency": "EUR", "price": ld_price}}
    qty = ('<select  id="prdqty" name="prdqty" class="x"><option value="500"  selected="selected" >500</option><option value="1000">1000</option></select>'
           if qty_select else "")
    return (f'<html><script type="application/ld+json">{json.dumps(ld)}</script>'
            '<label for="prdsize">Tama&ntilde;o</label><select name = "prdsize" id = "prdsize"><option selected="selected " value="1">DIN A6</option></select>'
            '<label for="aoptions[1]">Elige el papel<div class="d-none help"><div class="help_popup"><p>texto largo</p></div></div></label>'
            '<select name = "aoptions[1]" id = "aoptions[1]"><option value="9">Cuch&eacute; 130</option><option value="8">Otro</option></select>'
            f"{qty}"
            f'<input type="hidden" name="hidden_total_price" class="h" value="{net}"/><input type="hidden" name="taxAmt[]" value="{tax}"/>'
            f'<input type="hidden" id="total_price_with_tax" name="total_price_with_tax" value="{gross}"/></html>')


def test_printai_default_price_spec_and_first_option_fallback():
    result = printai.parse_page(pa_page())
    assert (result["name"], result["quantity"], result["net"], result["gross"]) == ("Flyers", 500, Decimal("31.24"), Decimal("37.8"))
    assert result["spec"] == [{"group": "Tamaño", "label": "DIN A6"}, {"group": "Elige el papel", "label": "Cuché 130"}]


@pytest.mark.parametrize("kwargs,message", [
    ({"net": "30.00"}, "differs from gross"),
    ({"ld_price": "99.00"}, "ld\\+json"),
    ({"qty_select": False}, "quantity"),
])
def test_printai_rejects_inconsistent_pages(kwargs, message):
    with pytest.raises(MatrixError, match=message):
        printai.parse_page(pa_page(**kwargs))


@pytest.fixture
def fake_pages(tmp_path, monkeypatch):
    robots = tmp_path / "robots.txt"
    robots.write_text("User-agent: *\nDisallow: /secret\n")
    pages, calls = {}, []

    def fake(url, cache_file, now, state, max_age_days=30, expected="xml"):
        meta = cache_file.with_suffix(".json")
        if cache_file.exists() and meta.exists():
            return cache_file.read_bytes(), True
        calls.append(url)
        state["requests"] = state.get("requests", 0) + 1
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(pages[url].encode("iso-8859-1" if "onlineprinters" in url else "utf-8"))
        meta.write_text(json.dumps({"fetched_at": now.isoformat()}))
        return cache_file.read_bytes(), False

    monkeypatch.setattr(sitemaps, "fetch_cached", fake)
    return tmp_path, robots, pages, calls


def test_collect_onlineprinters_and_printai_store_shared_offers(fake_pages):
    tmp, robots, pages, calls = fake_pages
    op, pa = "https://www.onlineprinters.es/p/flyers-a5", "https://www.printai.es/flyers/"
    pages[op], pages[pa] = op_page(), pa_page()
    db = tmp / "c.sqlite3"
    assert onlineprinters.collect(db, [op], tmp / "c1", robots, NOW)["pages"][0]["status"] == "ok"
    assert printai.collect(db, [pa], tmp / "c2", robots, NOW)["pages"][0]["status"] == "ok"
    assert onlineprinters.collect(db, [op], tmp / "c1", robots, NOW)["network_requests"] == 0
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT provider,quantity,price_kind,price,tax_status,shipping FROM supplier_offers ORDER BY provider,quantity").fetchall()
    assert rows == [("onlineprinters", 25, "total", "31.66", "net", "included"), ("onlineprinters", 1000, "total", "42.80", "net", "included"),
                    ("printai", 500, "total", "31.24", "net", "included")]


def test_collect_skips_bad_page_and_stops_on_challenge(fake_pages):
    tmp, robots, pages, calls = fake_pages
    ok, bad = "https://www.onlineprinters.es/p/ok", "https://www.onlineprinters.es/p/bad"
    pages[ok], pages[bad] = op_page(), "<html><title>x</title>sin datos</html>"
    report = onlineprinters.collect(tmp / "c.sqlite3", [ok, bad], tmp / "cache", robots, NOW)
    assert [p["status"] for p in report["pages"]] == ["ok", "failed"]
    pages[bad] = "<html>Just a moment...</html>"
    for f in (tmp / "cache").glob("p-bad*"):
        f.unlink()
    (tmp / "cache" / "bad.html").unlink(missing_ok=True)
    (tmp / "cache" / "bad.json").unlink(missing_ok=True)
    third = "https://www.onlineprinters.es/p/third"
    pages[third] = op_page()
    with pytest.raises(ValueError, match="challenge"):
        onlineprinters.collect(tmp / "c.sqlite3", [bad, third], tmp / "cache", robots, NOW)
    assert third not in calls


def test_robots_forbidden_route_is_never_requested(fake_pages):
    tmp, robots, pages, calls = fake_pages
    with pytest.raises(ValueError, match="robots"):
        printai.collect(tmp / "c.sqlite3", ["https://www.printai.es/secret/x"], tmp / "cache", robots, NOW)
    assert not calls


def test_replace_offers_is_atomic_and_replaces_old_rows(tmp_path):
    db = offers.connect(tmp_path / "o.sqlite3")
    row = {"quantity": 10, "kind": "unit", "price": "1.50", "currency": "EUR", "tax": "unknown", "shipping": "excluded", "scope": "t"}
    offers.replace_offers(db, "p", "u", "n", [row], "2026-10-27")
    offers.replace_offers(db, "p", "u", "n", [{**row, "price": "1.60"}, {**row, "quantity": 20}], "2026-11-27")
    assert db.execute("SELECT quantity,price FROM supplier_offers ORDER BY quantity").fetchall() == [(10, "1.60"), (20, "1.50")]
    with pytest.raises(sqlite3.IntegrityError):
        offers.replace_offers(db, "p", "u", "n", [{**row, "tax": "bogus"}], "x")
    assert db.execute("SELECT count(*) FROM supplier_offers").fetchone()[0] == 2  # failed replace rolled back


def test_redirected_pages_are_skipped_but_a_run_of_redirects_stops(fake_pages, monkeypatch):
    from app.collectors.discovery import Redirected
    tmp, robots, pages, calls = fake_pages
    base = "https://www.onlineprinters.es/p/"
    gone, ok = {base + "gone", base + "gone2"}, base + "ok"
    pages[ok] = op_page()
    inner = sitemaps.fetch_cached

    def moving(url, cache_file, now, state, max_age_days=30, expected="xml"):
        if url in gone or url.startswith(base + "moved"):
            raise Redirected(301, "https://www.onlineprinters.es")
        return inner(url, cache_file, now, state, max_age_days, expected)

    monkeypatch.setattr(sitemaps, "fetch_cached", moving)
    report = onlineprinters.collect(tmp / "c.sqlite3", [base + "gone", ok, base + "gone2"], tmp / "cache", robots, NOW)
    assert [p["status"] for p in report["pages"]] == ["failed", "ok", "failed"]
    assert "no longer available" in report["pages"][0]["error"]
    with sqlite3.connect(tmp / "c.sqlite3") as conn:
        assert conn.execute("SELECT count(*) FROM supplier_pages WHERE status='failed'").fetchone()[0] == 2
    seen = []
    with pytest.raises(ValueError, match="consecutive gone pages"):
        onlineprinters.collect(tmp / "d.sqlite3", [base + f"moved{i}" for i in range(9)], tmp / "cache2", robots, NOW,
                               log=lambda n, total, entry: seen.append(n))
    assert seen == [1, 2, 3, 4]  # the fifth consecutive redirect stops the run (no page worked before: no canary)
    with pytest.raises(ValueError, match="consecutive gone pages"):
        monkeypatch.setattr(sitemaps, "fetch_cached", lambda *a, **k: (_ for _ in ()).throw(Redirected(302, "https://x.test/captcha")))
        onlineprinters.collect(tmp / "e.sqlite3", [base + "one"], tmp / "cache3", robots, NOW)


def test_redirect_run_continues_if_canary_page_still_loads_but_stops_if_it_fails(fake_pages, monkeypatch):
    from app.collectors.discovery import Redirected
    tmp, robots, pages, calls = fake_pages
    base = "https://www.onlineprinters.es/p/"
    good, retired = base + "good", [base + f"gone{i}" for i in range(6)]
    pages[good] = op_page()
    inner, broken = sitemaps.fetch_cached, {"canary": False}

    def moving(url, cache_file, now, state, max_age_days=30, expected="xml"):
        if url in retired or (url == good and max_age_days == 0 and broken["canary"]):
            raise Redirected(301, "https://www.onlineprinters.es")
        return inner(url, cache_file, now, state, max_age_days, expected)

    monkeypatch.setattr(sitemaps, "fetch_cached", moving)
    report = onlineprinters.collect(tmp / "c.sqlite3", [good, *retired], tmp / "cache", robots, NOW)
    assert [p["status"] for p in report["pages"]] == ["ok"] + ["failed"] * 6  # five in a row did not stop the run
    broken["canary"] = True
    with pytest.raises(ValueError, match="canary page .* also fails"):
        onlineprinters.collect(tmp / "d.sqlite3", [good, *retired], tmp / "cache2", robots, NOW)


def test_http_404_is_a_gone_page_but_other_http_errors_stop_the_run(fake_pages, monkeypatch):
    from urllib.error import HTTPError
    tmp, robots, pages, calls = fake_pages
    base = "https://www.onlineprinters.es/p/"
    ok = base + "ok"
    pages[ok] = op_page()
    inner = sitemaps.fetch_cached

    def failing(url, cache_file, now, state, max_age_days=30, expected="xml"):
        if url.endswith("missing"):
            raise HTTPError(url, 404, "Not Found", {}, None)
        if url.endswith("forbidden"):
            raise HTTPError(url, 403, "Forbidden", {}, None)
        return inner(url, cache_file, now, state, max_age_days, expected)

    monkeypatch.setattr(sitemaps, "fetch_cached", failing)
    report = onlineprinters.collect(tmp / "c.sqlite3", [base + "missing", ok], tmp / "cache", robots, NOW)
    assert [p["status"] for p in report["pages"]] == ["failed", "ok"] and "HTTP 404" in report["pages"][0]["error"]
    with pytest.raises(HTTPError):
        onlineprinters.collect(tmp / "d.sqlite3", [ok, base + "forbidden", base + "after"], tmp / "cache", robots, NOW)
    assert base + "after" not in calls
    # same canonical-spelling rule: a redirect to the same path in another case is followed once
    from app.collectors import crawl
    assert crawl.same_page("https://x.test/es/producto/Camisa", "https://x.test/es/producto/camisa")
    assert not crawl.same_page("https://x.test/es/producto/camisa", "https://x.test/")
