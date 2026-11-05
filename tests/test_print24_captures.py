"""Import of a price-matrix capture copied from DevTools. ONLY synthetic numbers here (the real capture is checked in
test_print24_captures_real.py, which reads data/capturas/ and is skipped when it is not there)."""
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.web import create_app

CONFIG = {"format": "10 x 5 mm", "paper": "999 g/m² papel de prueba", "sides": "1 cara", "finishing": "Sin Acabados"}
KINDS = [("1001", 5, "standard"), ("1002", 4, "express"), ("1003", 1, "priority")]


def money(v):
    return f"{v:.2f}".replace(".", ",") + " €"


def matrix(quantities=((7, "q7", Decimal("1.00")), (9, "q9", Decimal("2.00"))), shipping=Decimal("0.50")):
    """Same shape as a real answer (array of {quantity:{id, shipping_type:[...]}}), invented numbers."""
    rows = []
    for units, qid, base in quantities:
        offers = []
        for index, (sid, days, kind) in enumerate(KINDS):
            product = base + index
            total, vat = product + shipping, (product + shipping) * Decimal("0.21")
            offers.append({"id": sid, "delivery_days": days, "delivery_type": kind, "delivery_text_translated": f"Entrega ficticia {kind}",
                           "price": {"currency": "EUR", "quantity_value": units, "final_prices": {
                               "product_net": money(product), "product_net_value": float(product), "shipping_net": money(shipping),
                               "total_net": money(total), "total_net_value": float(total), "total_vat": money(vat),
                               "total_gross_value": float(round(total + vat, 2))}}})
        rows.append({"quantity": {"id": qid, "shipping_type": offers}})
    return json.dumps(rows)


@pytest.fixture
def client(tmp_path):
    seed = tmp_path / "links.json"
    seed.write_text(json.dumps({"providers": {}}))
    with TestClient(create_app(tmp_path / "work.sqlite3", seed, tmp_path / "catalog.sqlite3")) as client:
        yield client


def post(client, response=None, configuration=CONFIG, payload=None):
    return client.post("/api/print24/captures/price-matrix", json={"response": response or matrix(), "configuration": configuration, "request_payload": payload})


def test_the_capture_is_stored_as_one_product_per_delivery_with_a_row_per_quantity(client):
    result = post(client, payload={"quantities": ["q7", "q9"], "product_alias_id": 1})
    assert result.status_code == 201, result.text
    body = result.json()
    assert (body["prices"], body["products"], body["quantities"]) == (6, 3, [7, 9])
    assert body["deliveries"] == ["express", "priority", "standard"]
    assert "Coinciden las 2 cantidades pedidas y recibidas" in body["checks"]
    items = client.get("/api/print24/captures").json()["items"]
    assert len(items) == 3
    standard = next(i for i in items if i["url"].endswith("-estandar"))
    assert [(r["quantity"], Decimal(r["total_net"]), r["delivery_days"]) for r in standard["rows"]] == [(7, Decimal("1.50"), 5), (9, Decimal("2.50"), 5)]
    assert any(s["group"] == "Origen" and "DevTools" in s["label"] for s in standard["spec"])
    assert any(s["label"] == CONFIG["paper"] for s in standard["spec"])  # the configuration is the one the person wrote


def test_an_imported_capture_can_be_queried_in_the_catalog_like_any_print24_product(client):
    post(client)
    data = client.get("/api/catalog", params={"provider": "print24", "limit": 50, "quantity": 7}).json()
    mine = [i for i in data["items"] if "#captura-" in i["url"]]
    assert len(mine) == 3
    assert all(i["provider"] == "print24" and i["tax_status"] == "net" and i["shipping"] == "included" for i in mine)
    assert {Decimal(i["prices"][0][1]) for i in mine} == {Decimal("1.50"), Decimal("2.50"), Decimal("3.50")}  # the 7-unit tier of each delivery


def test_importing_the_same_configuration_again_replaces_it(client):
    post(client)
    post(client, matrix(quantities=((7, "q7", Decimal("5.00")),)))
    items = client.get("/api/print24/captures").json()["items"]
    assert len(items) == 3
    assert all([r["quantity"] for r in i["rows"]] == [7] for i in items)
    assert Decimal(next(i for i in items if i["url"].endswith("-estandar"))["rows"][0]["total_net"]) == Decimal("5.50")
    post(client, configuration={**CONFIG, "paper": "otro papel de prueba"})  # another configuration is added, not replaced
    assert len(client.get("/api/print24/captures").json()["items"]) == 6


@pytest.mark.parametrize("secret", ["Cookie: a=b; c=d", "Auth: abcdef123456", "authorization: Bearer abcdefgh12345", "x?jwt=eyJ0eXAi"])
def test_text_that_looks_like_cookies_or_credentials_is_refused_and_nothing_is_stored(client, secret):
    assert post(client, response=matrix() + "\n" + secret).status_code == 422
    result = post(client, payload={"quantities": [], "note": secret, "user_identifier_token": "x"})
    assert result.status_code == 422 and "credenciales" in result.json()["detail"]
    assert client.get("/api/print24/captures").json()["items"] == []


def test_the_configuration_must_be_written_by_the_person(client):
    result = post(client, configuration={"format": "10 x 5 mm"})
    assert result.status_code == 422
    assert "el papel" in result.json()["detail"] and "las caras" in result.json()["detail"]
    assert client.get("/api/print24/captures").json()["items"] == []


def test_an_answer_that_does_not_fit_the_parser_stores_nothing_and_says_where(client):
    bad = json.loads(matrix())
    bad[1]["quantity"]["shipping_type"][0]["price"]["final_prices"]["shipping_net"] = "9,99 €"  # does not equal total - product
    for text in (json.dumps(bad), "no es json", "[]", json.dumps([{"quantity": {"id": "x"}}])):
        result = post(client, response=text)
        assert result.status_code == 422 and "price-matrix" in result.json()["detail"], text
    assert "row[1]" in post(client, response=json.dumps(bad)).json()["detail"]
    assert client.get("/api/print24/captures").json()["items"] == []


def test_quantities_of_the_payload_are_checked_against_the_answer(client):
    different = post(client, payload={"quantities": ["q7", "zzz"]}).json()["checks"]
    assert any("no coinciden" in note for note in different)
    assert any("No se pegó el Payload" in note for note in post(client).json()["checks"])


def test_the_test_page_says_it_is_a_manual_import_and_has_no_inline_script(client):
    page = client.get("/print24-test")
    assert page.status_code == 200
    assert "no una conexión en vivo" in page.text.lower() and "<script>" not in page.text
    assert client.get("/assets/print24-test.js").status_code == 200
    assert "Content-Security-Policy" in page.headers


def test_money_is_never_read_as_float():
    from app.parsers.price_matrix import parse_matrix
    prices = parse_matrix(matrix(quantities=((7, "q7", Decimal("0.10")),)))
    assert all(isinstance(p.total_net, Decimal) for p in prices)
    assert prices[0].total_net == Decimal("0.60")


def test_a_configuration_whose_name_starts_like_another_does_not_erase_it(client):
    post(client, configuration={**CONFIG, "finishing": "Barniz"})
    post(client, configuration={**CONFIG, "finishing": "Barniz protector"})
    post(client, matrix(quantities=((7, "q7", Decimal("8.00")),)), configuration={**CONFIG, "finishing": "Barniz"})  # replaces only its own
    items = client.get("/api/print24/captures").json()["items"]
    assert len(items) == 6
    longer = [i for i in items if "barniz-protector" in i["url"]]
    assert len(longer) == 3 and all(len(i["rows"]) == 2 for i in longer)
