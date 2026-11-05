"""Read-only WooCommerce import. Fake shop, fake keys: nothing here talks to a real shop or holds a real key."""
import base64
import json
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from app.collectors import offers, woocommerce as woo

KEY, SECRET = "ck_" + "a" * 20, "cs_" + "b" * 20
ENV = {"WOO_URL": "https://shop.example.test", "WOO_KEY": KEY, "WOO_SECRET": SECRET}


class Response:
    def __init__(self, data, headers=None):
        self.body, self.headers = json.dumps(data).encode(), headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self.body


class Opener:
    """Answers like the shop: 150 products over two pages and 2 categories; records every request."""
    def __init__(self, fail=None, products=None):
        self.requests, self.fail = [], fail
        self.products = products if products is not None else [product(i) for i in range(1, 151)]

    def open(self, req, timeout=None):
        self.requests.append(req)
        if self.fail:
            raise self.fail
        url = req.full_url
        if "/products/categories" in url:
            return Response([{"id": 7, "name": "Tarjetas &amp; flyers", "slug": "tarjetas", "parent": 0, "count": 3}])
        page = int(parse_qs(urlsplit(url).query)["page"][0])
        chunk = self.products[(page - 1) * 100: page * 100]
        return Response(chunk, {"X-WP-TotalPages": str((len(self.products) + 99) // 100)})


def product(i, status="publish", url=None):
    return {"id": i, "name": f"Producto <b>{i}</b>", "slug": f"p{i}", "permalink": url or f"https://shop.example.test/p{i}/", "type": "simple",
            "status": status, "sku": f"S{i}", "price": "9.5", "regular_price": "10", "sale_price": "9.5", "on_sale": True, "stock_status": "instock",
            "stock_quantity": None, "categories": [{"id": 7, "name": "Tarjetas &amp; flyers"}], "short_description": "<p>Corta</p>",
            "description": "<p>Larga &amp; con <em>html</em></p>", "images": [{"src": f"https://shop.example.test/img{i}.jpg"}], "date_modified": "2026-11-01T10:00:00"}


def test_credentials_must_be_real_https_and_well_formed():
    assert woo.credentials(ENV) == ("https://shop.example.test", KEY, SECRET)
    for bad in ({**ENV, "WOO_KEY": ""}, {**ENV, "WOO_SECRET": ""}, {**ENV, "WOO_KEY": "ck_pega_aqui_la_clave"}, {**ENV, "WOO_KEY": "xx_123"},
                {**ENV, "WOO_URL": "http://shop.example.test"}, {**ENV, "WOO_URL": ""}):
        with pytest.raises(woo.WooError):
            woo.credentials(bad)


def test_env_file_is_parsed_and_the_real_environment_wins(tmp_path, monkeypatch):
    file = tmp_path / ".env"
    file.write_text('# comentario\nWOO_URL="https://a.test"\n\nWOO_KEY=ck_x\nWOO_SECRET = cs_y \n', encoding="utf-8")
    monkeypatch.delenv("WOO_KEY", raising=False)
    monkeypatch.delenv("WOO_URL", raising=False)
    monkeypatch.delenv("WOO_SECRET", raising=False)
    assert woo.load_env(file) == {"WOO_URL": "https://a.test", "WOO_KEY": "ck_x", "WOO_SECRET": "cs_y"}
    monkeypatch.setenv("WOO_KEY", "ck_env")
    assert woo.load_env(file)["WOO_KEY"] == "ck_env"
    assert woo.load_env(tmp_path / "no-existe.env") == {"WOO_KEY": "ck_env"}


def test_only_products_and_categories_are_ever_asked_with_get_and_basic_auth():
    opener = Opener()
    woo.run(woo_db := None or __import__("pathlib").Path(__import__("tempfile").mkdtemp()) / "c.sqlite3", ENV, opener, pause=lambda: None)
    assert opener.requests and all(r.get_method() == "GET" for r in opener.requests)
    assert all(r.full_url.startswith("https://shop.example.test/wp-json/wc/v3/products") for r in opener.requests)
    assert not any("orders" in r.full_url or "customers" in r.full_url for r in opener.requests)
    token = base64.b64decode(opener.requests[0].get_header("Authorization").split()[1]).decode()
    assert token == f"{KEY}:{SECRET}"
    assert KEY not in opener.requests[0].full_url and SECRET not in opener.requests[0].full_url  # never in the address
    with pytest.raises(woo.WooError, match="no permitida"):
        woo.request("https://shop.example.test", KEY, SECRET, "orders", opener=opener)
    with pytest.raises(woo.WooError, match="no permitida"):
        woo.request("https://shop.example.test", KEY, SECRET, "customers", opener=opener)


def test_every_page_is_read_with_a_pause_between_them_and_stored(tmp_path):
    pauses = []
    opener = Opener()
    summary = woo.run(tmp_path / "c.sqlite3", ENV, opener, pause=lambda: pauses.append(1))
    assert summary["products"] == 150 and summary["categories"] == 1
    assert len(pauses) == 1  # two product pages: one pause between them (a single category page needs none)
    rows = woo.list_products(tmp_path / "c.sqlite3", "", 500)
    assert len(rows) == 150
    first = next(r for r in rows if r["id"] == 1)
    assert first["name"] == "Producto 1"  # no html
    assert first["description"] == "Larga & con html" and first["short_description"] == "Corta"
    assert first["categories"] == [{"id": 7, "name": "Tarjetas & flyers"}] and first["price"] == "9.5" and first["on_sale"] == 1
    assert first["image_url"].endswith("img1.jpg") and first["stock_quantity"] is None


def test_a_second_import_replaces_the_first_and_a_failure_keeps_the_old_data(tmp_path):
    db = tmp_path / "c.sqlite3"
    woo.run(db, ENV, Opener(products=[product(1), product(2)]), pause=lambda: None)
    woo.run(db, ENV, Opener(products=[product(3)]), pause=lambda: None)
    assert [r["id"] for r in woo.list_products(db, "", 50)] == [3]
    with pytest.raises(woo.WooError):
        woo.run(db, ENV, Opener(fail=HTTPError("https://x", 500, "boom", {}, None)), pause=lambda: None)
    assert [r["id"] for r in woo.list_products(db, "", 50)] == [3]


@pytest.mark.parametrize("code,word", [(401, "no son válidas"), (403, "permiso de lectura"), (404, "no está disponible")])
def test_errors_are_readable_and_never_show_the_keys(code, word):
    error = HTTPError(f"https://shop.example.test/wp-json/wc/v3/products?consumer_key={KEY}", code, "x", {"Authorization": KEY}, None)
    with pytest.raises(woo.WooError) as caught:
        woo.request("https://shop.example.test", KEY, SECRET, "products", opener=Opener(fail=error))
    assert word in str(caught.value) and KEY not in str(caught.value) and SECRET not in str(caught.value)


def test_a_redirect_is_refused_so_the_key_never_travels_elsewhere():
    from app.collectors.discovery import Redirected
    with pytest.raises(woo.WooError, match="no se envía la clave"):
        woo.request("https://shop.example.test", KEY, SECRET, "products", opener=Opener(fail=Redirected(301, "https://evil.test/")))


def test_a_page_that_is_not_json_is_reported(tmp_path):
    class Html(Opener):
        def open(self, req, timeout=None):
            r = Response([])
            r.body = b"<html>captcha</html>"
            return r
    with pytest.raises(woo.WooError, match="JSON"):
        woo.request("https://shop.example.test", KEY, SECRET, "products", opener=Html())


def test_coverage_says_which_published_products_have_prices_only_a_link_or_nothing(tmp_path):
    db = tmp_path / "c.sqlite3"
    items = [product(1, url="https://shop.example.test/con-precio/"), product(2, url="https://www.shop.example.test/solo-enlace"),
             product(3, url="https://shop.example.test/falta/"), product(4, status="draft", url="https://shop.example.test/borrador/")]
    woo.store(db, items, [], datetime(2026, 11, 5, tzinfo=timezone.utc))
    conn = offers.connect(db)
    offers.replace_offers(conn, "laimprentadeinternet", "https://shop.example.test/con-precio/#config-a", "X", [
        {"quantity": 1, "kind": "total", "price": "5", "currency": "EUR", "tax": "net", "shipping": "included", "scope": "t"}], "2026-11-05")
    offers.record_page(conn, "laimprentadeinternet", "https://shop.example.test/solo-enlace/", "2026-11-05", "failed", 0, "ficha propia sin precio recogido")
    conn.close()
    report = woo.coverage(db)
    assert [p["name"] for p in report["with_prices"]] == ["Producto 1"]
    assert [p["name"] for p in report["link_only"]] == ["Producto 2"]  # www and trailing slash do not matter
    assert [p["name"] for p in report["missing"]] == ["Producto 3"]  # the draft is not counted


def test_the_local_api_lists_the_shop_products_and_the_coverage(tmp_path):
    from fastapi.testclient import TestClient
    from app.api.web import create_app
    seed = tmp_path / "links.json"
    seed.write_text(json.dumps({"providers": {}}))
    woo.store(tmp_path / "catalog.sqlite3", [product(1), product(2)], [], datetime(2026, 11, 5, tzinfo=timezone.utc))
    with TestClient(create_app(tmp_path / "work.sqlite3", seed, tmp_path / "catalog.sqlite3")) as client:
        listed = client.get("/api/shop/products", params={"q": "producto 2"}).json()["items"]
        assert [i["id"] for i in listed] == [2]
        assert set(client.get("/api/shop/coverage").json()) == {"with_prices", "link_only", "missing"}
        assert "consumer" not in client.get("/api/shop/products").text.lower()  # nothing secret is ever served
