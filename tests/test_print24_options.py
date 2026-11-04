from decimal import Decimal
from types import SimpleNamespace

from app.collectors import print24_options as o

TEXTS = ["Tarjetas de visita", "1 cara", "Formato 85 x 55 mm", "Horizontal", "350 g/m² Papel estucado Couché brillante", "4+0 tintas (CMYK)",
         "Cortar", "Plastificado", "1 cara Brillante", "Sin prueba", "100 Unidades"]


def price(kind, quantity, total, days="5"):
    return SimpleNamespace(delivery_type=kind, delivery_days=days, quantity_value=quantity, total_net=Decimal(total))


def test_every_list_of_the_configurator_is_recognised_by_its_text():
    assert [o.box_index(TEXTS, k) for k in ("sides", "format", "orientation", "paper", "inks", "finishing", "proof", "quantity")] == [1, 2, 3, 4, 5, 7, 9, 10]
    assert o.box_index(["Tarjetas de visita"], "paper") is None


def test_the_state_is_what_the_page_shows_and_finishing_keeps_its_sub_lists():
    state = o.read_state(TEXTS)
    assert state == {"sides": "1 cara", "format": "85 x 55 mm", "orientation": "Horizontal", "paper": "350 g/m² Papel estucado Couché brillante",
                     "inks": "4+0 tintas (CMYK)", "finishing": "Plastificado · 1 cara Brillante"}


def test_products_are_one_per_delivery_type_with_the_cheapest_total_of_each_quantity():
    state = o.read_state(TEXTS[:7] + ["Sin Acabados", "Sin prueba", "100 Unidades"])
    matrix = [price("standard", 100, "13.10"), price("express", 100, "19.28", "4"), price("standard", 250, "14.00"), price("standard", 100, "13.50")]
    products = o.build_products("https://print24.com/es/x", "Tarjetas de visita", state, matrix)
    assert [p["rows"][0]["delivery_days"] for p in products] == [5, 4]  # standard first
    standard = products[0]
    assert [(r["quantity"], r["price"]) for r in standard["rows"]] == [(100, Decimal("13.10")), (250, Decimal("14.00"))]
    assert standard["rows"][0]["tax"] == "net" and standard["rows"][0]["shipping"] == "included"
    assert {"group": "Acabados", "label": "sin acabado"} in standard["spec"] and {"group": "Impresión", "label": "1 cara · 4+0 tintas (CMYK)"} in standard["spec"]
    assert standard["url"].startswith("https://print24.com/es/x#") and standard["url"] != products[1]["url"]


def test_the_option_a_page_already_shows_is_added_to_its_list_and_only_wanted_ones_stay():
    assert o.with_current(["2 caras", "4 caras"], "1 cara", o.SIDES_WANTED) == ["1 cara", "2 caras"]
    assert o.with_current(["300 g", "250 g"], "350 g") == ["350 g", "300 g", "250 g"]
    assert o.with_current(["Barniz protector (recomendado)", "Relieve en seco"], "Sin Acabados", o.FINISHING_WANTED) == ["Sin Acabados", "Barniz protector (recomendado)"]


def test_configurations_are_cut_at_the_limit_with_the_papers_outermost():
    combos, cut = o.configurations(["1 cara", "2 caras"], ["a", "b"], ["x", "y"], limit=5)
    assert len(combos) == 5 and cut and combos[0] == ("1 cara", "a", "x") and combos[4] == ("1 cara", "b", "x")


def test_a_print24_page_read_option_by_option_hides_its_default_item(tmp_path):
    from app.collectors import offers
    from app.services.workbench import _read_items
    from tests.test_web import make_catalog
    cat = tmp_path / "catalog.sqlite3"
    make_catalog(cat)
    url = next(i["url"] for i in _read_items(cat)[0] if i["provider"] == "print24")
    db = offers.connect(cat)
    offers.replace_offers(db, "print24", f"{url}#config", "Tarjetas · combinacion", [
        {"quantity": 100, "kind": "total", "price": "13.10", "currency": "EUR", "tax": "net", "shipping": "included", "scope": "t"}], "2026-11-04", [])
    db.close()
    items = [i for i in _read_items(cat)[0] if i["provider"] == "print24"]
    assert [i["url"] for i in items] == [f"{url}#config"]  # the default item of the page is not repeated
