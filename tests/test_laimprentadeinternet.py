import json
from decimal import Decimal

from app.collectors import laimprentadeinternet as shop
from app.collectors import offers

PAGE = """<html><script type="application/ld+json">{"@graph":[{"@type":"Product","name":"Tarjetas de Visita",
"description":"Tarjetas con formato estándar de 85x55 mm en papel estucado de 350 gr con certificación FSC."}]}</script>
<input type="hidden" name="cpo_product_id" value="683">
<select name="uni_cpo_tarjetas_unidades"><option value="">Por favor, selecciona...</option><option value="a100">
100</option><option value="a500">500</option></select>
<select name="uni_cpo_caras_impresas_tarjeta"><option value="">Por favor, selecciona...</option><option value="a1_cara">1 cara</option><option value="a2_caras">2 caras</option></select>
<select name="uni_cpo_acabado_tarjetas"><option value="">Por favor, selecciona...</option><option value="sin">Sin</option><option value="pl">Plastificado 1 cara</option></select>
<select name="uni_cpo_diseno_tarjetasvisita"><option value="">Por favor, selecciona...</option><option value="rev">revisión gratis</option><option value="art">artes finales +15€</option></select>
<select name="uni_cpo_envio_tarjetavisita"><option value="">Por favor, selecciona...</option><option value="std">7-10 días gratis</option><option value="exp">2-3 días +35€</option></select>
</html>"""


def test_form_and_description_are_read_from_the_page():
    form = shop.parse_form(PAGE)
    assert [f["name"] for f in form][:2] == ["uni_cpo_tarjetas_unidades", "uni_cpo_caras_impresas_tarjeta"]
    assert form[0]["options"] == [{"value": "a100", "label": "100"}, {"value": "a500", "label": "500"}]  # no placeholder
    info = shop.describe(PAGE)
    assert info["product_id"] == "683" and "350 gr" in info["description"]


def test_every_step_changes_exactly_one_select_and_the_design_service_is_fixed():
    combos = shop.combinations(shop.parse_form(PAGE))
    assert len(combos) == 2 * 2 * 2 * 1 * 2 and len({shop.key_of(c) for c in combos}) == len(combos)
    assert all(sum(a[k] != b[k] for k in a) == 1 for a, b in zip(combos, combos[1:]))
    assert {c["uni_cpo_diseno_tarjetasvisita"] for c in combos} == {"rev"}


def test_delivery_text_becomes_days():
    assert shop.days_in("7-10 días gratis") == (10, "7-10 días hábiles")
    assert shop.days_in("2-3 días +35€") == (3, "2-3 días hábiles")
    assert shop.days_in("Sin") == (None, "")


def test_products_carry_the_characteristics_the_card_filters_read(tmp_path):
    form, info = shop.parse_form(PAGE), shop.describe(PAGE)
    prices = {shop.key_of(c): {"net": 10 + i, "gross": 12.1 + i} for i, c in enumerate(shop.combinations(form))}
    products = shop.build_offers("https://laimprentadeinternet.com/tarjetas/", info, form, prices)
    assert len(products) == 2 * 2 * 2  # sides x finish x delivery, each with a tier per quantity
    first = products[0]
    assert [r["quantity"] for r in first["rows"]] == [100, 500] and all(r["tax"] == "net" and r["shipping"] == "included" for r in first["rows"])
    labels = {(x["group"], x["label"]) for x in first["spec"]}
    assert ("Formato", "85 x 55 mm") in labels and ("Papel", "350 g/m² papel estucado") in labels
    assert ("Impresión", "4+0 una cara") in labels and ("Acabados", "sin acabado") in labels
    assert len({p["url"] for p in products}) == len(products)  # one address per configuration: each is replaced on its own

    from app.services.cards import entry_matches
    entry = {"url": first["url"], "title": first["name"], "spec": first["spec"], "provider": shop.PROVIDER}
    basic = {"format": "85 x 55 mm", "material": "350 g/m² Estucado / cuché", "printing": "Sin especificar", "finishing": "Sin",
             "extras": {"pages": "1 cara", "type": "Estándar"}}
    assert entry_matches(entry, basic, shop.PROVIDER)  # the shop's standard card is the standard card
    assert not entry_matches(entry, {**basic, "extras": {"pages": "2 caras"}}, shop.PROVIDER)

    db = offers.connect(tmp_path / "c.sqlite3")
    for product in products:
        offers.replace_offers(db, shop.PROVIDER, product["url"], product["name"], product["rows"], "2026-11-03", product["spec"])
    assert db.execute("SELECT count(DISTINCT product_url), count(*) FROM supplier_offers").fetchone() == (8, 16)
    assert Decimal(db.execute("SELECT price FROM supplier_offers ORDER BY product_url, quantity LIMIT 1").fetchone()[0]) > 0
    db.close()


def test_the_shop_is_a_provider_marked_as_ours():
    from app.services.workbench import PROVIDERS
    ours = [p for p in PROVIDERS if p.get("own")]
    assert [p["id"] for p in ours] == [shop.PROVIDER]
