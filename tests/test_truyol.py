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


def test_formats_with_a_din_name_keep_it_and_get_millimetres():
    assert t.format_label("A5 Vertical (14,8x21cm)") == "A5 (148 x 210 mm)"
    assert t.format_label("A7 (7,4x10,5cm)") == "A7 (74 x 105 mm)"
    assert t.format_label("9,8x21cm") == "98 x 210 mm"


def test_configurations_are_the_product_of_what_the_page_offers_and_are_cut():
    options = {"format": ["a", "b"], "paper": ["x", "y", "z"], "sides": ["1C"], "lamination": []}
    combos, cut = t.configurations(options)
    assert len(combos) == 6 and not cut and combos[0] == {"format": "a", "paper": "x"}
    combos, cut = t.configurations(options, limit=4)
    assert len(combos) == 4 and cut
    assert t.configurations({"sides": ["1C"]}) == ([{}], False)


def test_varied_format_and_paper_go_in_the_name_so_addresses_never_collide():
    one = {"format": "A6 (14,8x10,5cm)", "paper": "Estucado Mate 130 g/m2", "sides": "1C"}
    two = {"format": "A5 Vertical (14,8x21cm)", "paper": "Estucado Mate 130 g/m2", "sides": "1C"}
    prices = {("24H", 1000): Decimal("30.00")}
    a = t.build_products("https://truyol.com/es/flyers", "Flyers", one, prices, ("format", "paper"))[0]["url"]
    b = t.build_products("https://truyol.com/es/flyers", "Flyers", two, prices, ("format", "paper"))[0]["url"]
    assert a != b


def test_the_discount_of_the_page_is_applied_and_checked_against_the_gross_price():
    # list 215.11, 15 % off -> 182.84 net, 221.24 gross (what the page shows as the price)
    rows, bad = t.price_rows([{**button("24H", 5000, "215.11", "221.24"), "dto": "15.00", "dto_max": "1000"}])
    assert rows == {("24H", 5000): Decimal("182.84")} and bad == 0
    # the discount is capped at dto_max euros
    rows, bad = t.price_rows([{**button("24H", 5000, "1000.00", "1089.00"), "dto": "15.00", "dto_max": "100"}])
    assert rows == {("24H", 5000): Decimal("900.00")} and bad == 0
    # a discount that does not explain the gross price is dropped
    rows, bad = t.price_rows([{**button("24H", 5000, "215.11", "260.28"), "dto": "15.00", "dto_max": "1000"}])
    assert rows == {} and bad == 1
