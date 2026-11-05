"""Flyers, brochures (stapled, tri-fold, bi-fold) of our own shop: forms shaped like the real ones, invented prices."""
import re

import pytest

from app.collectors import laimprentadeinternet as shop


def select(name, options):
    body = "".join(f'<option value="{v}">{label}</option>' for v, label in options)
    return f'<select name="{name}"><option value="">Por favor, selecciona...</option>{body}</select>'


def page(name, description, *selects):
    return (f'<script type="application/ld+json">{{"@graph":[{{"@type":"Product","name":"{name}","description":"{description}"}}]}}</script>'
            + "".join(selects))


FLYERS = page("Flyers", "Selecciona tus opciones en A5, A6 o DL sobre papel estucado de 135g (brillo o mate).",
              select("uni_cpo_unidades_flyers", [("u1", "1000"), ("u2", "2000"), ("u5", "5000")]),
              select("uni_cpo_tamano_flyers", [("a6", "A6 105x148mm"), ("dl", "DL 100x210mm"), ("a5", "A5 148x210mm")]),
              select("uni_cpo_caras_flyers", [("c1", "1 cara"), ("c2", "2 caras")]),
              select("uni_cpo_diseno_flyer", [("rev", "revisión gratis"), ("art", "artes finales +25€")]),
              select("uni_cpo_envio_flyer", [("std", "7-10 días gratis"), ("exp", "2-3 días +24€")]))
STAPLED = page("Folletos grapados", "Se realizan en papel estucado de 135gr (brillo o mate), en tamaño A4 o A5 de 8, 12 o 16 páginas.",
               select("uni_cpo_unidades_folletos", [("u50", "50"), ("u100", "100")]),
               select("uni_cpo_tamano_folletos", [("a5", "A5 cerrado"), ("a4", "A4 cerrado")]),
               select("uni_cpo_paginas_folletos", [("p8", "8 pag"), ("p12", "12 pag"), ("p16", "16 pag")]))
TRIPTYCH = page("Trípticos", "La impresión de folletos trípticos ofrece 6 caras de comunicación.",
                select("uni_cpo_unidades_tripticos", [("u100", "100"), ("u250", "250")]),
                select("uni_cpo_tamano_tripticos", [("dl", "100x210mm cerrado"), ("a5", "A5 cerrado")]),
                select("uni_cpo_diseno_triptico", [("rev", "revisión gratis"), ("art", "artes finales +35€")]),
                select("uni_cpo_envio_triptico", [("std", "7-10 días gratis"), ("exp", "2-3 días +40€")]))


def products_of(html):
    form, info = shop.parse_form(html), shop.describe(html)
    prices = {shop.key_of(c): {"net": 10 + i, "gross": 12.1 + i} for i, c in enumerate(shop.combinations(form))}
    return shop.build_offers("https://example.test/p/", info, form, prices), form


def test_the_brochure_pages_are_collected_with_the_cards():
    names = [u.rsplit("/", 2)[-2] for u in shop.PAGES]
    for wanted in ("impresion-de-flyers-publicitarios", "impresion-de-folletos", "impresion-de-folletos-tripticos", "impresion-dipticos"):
        assert wanted in names
    assert "impresion-de-tarjetas-de-visita" in names


@pytest.mark.parametrize("label,expected", [("A6 105x148mm", "A6 105 x 148 mm"), ("DL 100x210mm", "DL 100 x 210 mm"),
                                            ("100x210mm cerrado", "100 x 210 mm cerrado"), ("A5 cerrado", "A5 cerrado")])
def test_size_labels_read_like_the_other_providers(label, expected):
    assert shop.size_label(label) == expected


def test_flyers_have_one_product_per_size_sides_and_delivery_with_a_row_per_quantity():
    products, form = products_of(FLYERS)
    assert len(products) == 3 * 2 * 2  # size x sides x delivery (the design service is fixed)
    assert all([r["quantity"] for r in p["rows"]] == [1000, 2000, 5000] for p in products)
    assert len({p["url"] for p in products}) == len(products)  # no two configurations share an address (one would erase the other)
    labels = [{(x["group"], x["label"]) for x in p["spec"]} for p in products]
    assert any(("Formato", "A6 105 x 148 mm") in l and ("Impresión", "4+0 una cara") in l for l in labels)
    assert all(("Papel", "135 g/m² papel estucado") in l for l in labels)  # said in the page text
    assert not any(g == "Formato" and "x  mm" in label for l in labels for g, label in l)


def test_stapled_brochures_have_their_pages_in_the_name_and_the_spec():
    products, _ = products_of(STAPLED)
    assert len(products) == 2 * 3 and len({p["url"] for p in products}) == 6
    first = products[0]
    assert "8 páginas" in first["name"] and ("Páginas", "8 páginas") in {(x["group"], x["label"]) for x in first["spec"]}
    assert not any(x["group"] == "Plazo de producción" for x in first["spec"])  # this page has no delivery select: nothing invented
    assert first["rows"][0]["delivery_days"] is None


def test_a_page_without_paper_text_gets_no_invented_paper():
    products, _ = products_of(TRIPTYCH)
    assert len(products) == 2 * 2
    assert not any(x["group"] == "Papel" for p in products for x in p["spec"])
    assert any(x["group"] == "Formato" and x["label"] == "100 x 210 mm cerrado" for p in products for x in p["spec"])


def test_an_unknown_select_is_kept_as_a_characteristic_so_names_never_collide():
    html = page("Algo", "Un producto.", select("uni_cpo_unidades_algo", [("u1", "10")]),
                select("uni_cpo_plegado_algo", [("env", "Envolvente"), ("zig", "Zig-zag")]))
    products, _ = products_of(html)
    assert len(products) == 2 and len({p["url"] for p in products}) == 2
    assert {(x["group"], x["label"]) for p in products for x in p["spec"]} >= {("Plegado", "Envolvente"), ("Plegado", "Zig-zag")}


def test_number_of_combinations_matches_the_real_forms_sizes():
    # real forms: flyers 5 quantities x 3 sizes x 2 sides x 2 deliveries = 60; stapled 5 x 2 x 3 = 30 (checked against the live pages)
    f = lambda n, k: {"name": n, "options": [{"value": str(i), "label": str(i)} for i in range(k)]}
    assert len(shop.combinations([f("uni_cpo_unidades_flyers", 5), f("uni_cpo_tamano_flyers", 3), f("uni_cpo_caras_flyers", 2),
                                  f("uni_cpo_diseno_flyer", 3), f("uni_cpo_envio_flyer", 2)])) == 60
    assert len(shop.combinations([f("uni_cpo_unidades_folletos", 5), f("uni_cpo_tamano_folletos", 2), f("uni_cpo_paginas_folletos", 3)])) == 30
