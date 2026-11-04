from decimal import Decimal

from app.collectors import truyol as t


def button(plazo, cnt, net, gross, iva="21"):
    return {"plazo": plazo, "cnt": str(cnt), "precio": net, "precio_con_iva": gross, "iva": iva}


def test_price_rows_keep_only_consistent_net_and_gross_prices():
    rows, bad = t.price_rows([button("24H", 100, "23.669999999999998", "28.64"), button("2-3D", 100, "21.45", "25.95"),
                              button("4-5D", 100, "19.96", "99.00"),  # gross does not match net + VAT
                              button("6-7D", 100, "-1", "-1.21"), {"plazo": "6-7D", "cnt": "x"}])
    assert rows == {("24H", 100): Decimal("23.67"), ("2-3D", 100): Decimal("21.45")}
    assert bad == 3


def test_price_rows_first_value_wins_for_a_repeated_quantity():
    rows, _ = t.price_rows([button("24H", 500, "30.00", "36.30"), button("24H", 500, "31.00", "37.51")])
    assert rows == {("24H", 500): Decimal("30.00")}


def test_labels_use_the_wording_of_the_other_providers():
    assert t.format_label("8,5x5,5cm") == "85 x 55 mm"
    assert t.format_label("21x29,7cm") == "210 x 297 mm"
    assert t.format_label("A5") == "A5"
    assert t.paper_label("Estucado Mate 350 g/m2") == "350 g/m² papel estucado mate"


def test_describe_and_products_one_per_delivery_time():
    selected = {"format": "8,5x5,5cm", "paper": "Estucado Mate 350 g/m2", "sides": "1C", "lamination_text": "No"}
    name, spec = t.describe(selected, "2-3D")
    assert name == "4+0 una cara · Sin acabado · 2 a 3 días"
    assert {"group": "Acabados", "label": "sin acabado"} in spec and {"group": "Formato", "label": "85 x 55 mm"} in spec
    prices = {("24H", 100): Decimal("23.67"), ("24H", 250): Decimal("27.58"), ("6-7D", 100): Decimal("19.23")}
    products = t.build_products("https://truyol.com/es/x", "Tarjetas", selected, prices)
    assert [p["rows"][0]["delivery_days"] for p in products] == [1, 7]  # fastest first
    first = products[0]
    assert [r["quantity"] for r in first["rows"]] == [100, 250]
    assert first["rows"][0]["tax"] == "net" and first["rows"][0]["shipping"] == "included"
    assert first["url"].startswith("https://truyol.com/es/x#") and first["name"].startswith("Tarjetas · ")


def test_the_collector_refuses_a_forbidden_route(tmp_path):
    import pytest
    from app.collectors.index_homepages import navigation_allowed
    robots = "User-agent: *\nDisallow: /files/\nDisallow: /*.pdf\nAllow: /\n"
    assert navigation_allowed(robots, t.CARDS)
    assert not navigation_allowed(robots, "https://truyol.com/files/catalogo.pdf")
    assert pytest is not None
