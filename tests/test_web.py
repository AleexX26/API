import json
from decimal import Decimal
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.api.web import create_app
from app.collectors.index_homepages import Navigation, navigation_allowed


@pytest.fixture
def client(tmp_path):
    seed = tmp_path / "links.json"
    seed.write_text(json.dumps({"providers":{"print24":{"status":"indexed","links":[{"title":"Flyers","url":"https://print24.com/es/flyers"}]}}}))
    with TestClient(create_app(tmp_path / "work.sqlite3", seed)) as client:
        yield client


BRIEF = {"query":"flyers","quantity":1000,"format":"A5","material":"Estucado 135 g/m²","printing":"Color · dos caras","finishing":"Sin especificar","max_days":30,"country":"ES"}


def quote(provider="print24", **changes):
    return {"brief":BRIEF,"provider":provider,"product_net":"100.10","shipping_net":"10.20","additional_net":"0.00","delivery_days":6,"valid_until":"2099-12-31","source_url":"https://print24.com/es/flyers" if provider=="print24" else "https://truyol.com/","notes":"Test only","confirmed_equivalent":True,**changes}


def test_search_no_synthetic_prices(client):
    response = client.post('/api/search', json={"brief":BRIEF})
    assert response.status_code == 200
    result = response.json()
    assert len(result['providers']) == 6
    assert result['providers'][0]['matched_links'] == 1
    assert not result['winners']
    assert all(not p['quotes'] for p in result['providers'])
    assert client.get('/').status_code == 200
    assert client.get('/assets/app.js').status_code == 200


def test_quote_exact_comparison_and_unknown_shipping(client):
    assert client.post('/api/quotes',json=quote()).status_code==201
    assert client.post('/api/quotes',json=quote('truyol',shipping_net=None,product_net="1.00")).status_code==201
    r=client.post('/api/search',json={"brief":BRIEF}).json()
    assert r['providers'][0]['best']['total_net']=="110.30"
    assert r['providers'][1]['best'] is None
    assert r['winners']==[]
    assert client.post('/api/quotes',json=quote('truyol',product_net="80.00")).status_code==201
    r=client.post('/api/search',json={"brief":BRIEF}).json()
    assert r['winners']==['truyol']
    different={**BRIEF,"quantity":500}
    assert client.post('/api/search',json={"brief":different}).json()['comparable_providers']==0


def test_expired_late_and_cross_origin(client):
    client.post('/api/quotes',json=quote(valid_until="2000-01-01"))
    client.post('/api/quotes',json=quote(delivery_days=90))
    assert client.post('/api/search',json={"brief":BRIEF}).json()['comparable_providers']==0
    assert client.post('/api/quotes',json=quote(),headers={'origin':'https://other.test'}).status_code==403
    assert client.post('/api/quotes',json=quote(source_url='https://evil.test/')).status_code==422
    assert client.post('/api/quotes',json=quote(product_net='NaN')).status_code==422
    assert client.post('/api/quotes',json=quote(confirmed_equivalent=False)).status_code==422


def test_revised_quote_preserves_history_but_does_not_rank_old_price(client):
    client.post('/api/quotes',json=quote(product_net="1.00"))
    client.post('/api/quotes',json=quote(product_net="200.00"))
    result=client.post('/api/search',json={"brief":BRIEF}).json()
    provider=result['providers'][0]
    assert len(provider['quotes'])==2
    assert provider['quotes'][1]['superseded']
    assert provider['best']['product_net']=='200.00'


def test_homepage_parser_and_applicable_robots():
    parser=Navigation('https://truyol.com/')
    parser.feed('<a href="/flyers">Flyers <b>A5</b></a><a href="/login">Login</a><a href="https://evil.test/">Outside</a>')
    assert parser.links=={'https://truyol.com/flyers':'Flyers A5'}
    rules='User-agent: *\nDisallow: /files/\nAllow: /\nUser-agent: OtherBot\nDisallow: /'
    assert navigation_allowed(rules,'https://truyol.com/')
    assert not navigation_allowed(rules,'https://truyol.com/files/a')
    assert navigation_allowed('User-agent: OtherBot\nDisallow: /','https://truyol.com/')
    assert not navigation_allowed('User-agent: PrintWorkbenchResearch\nDisallow: /','https://truyol.com/')


def make_catalog(path):
    import sqlite3
    from datetime import datetime, timezone
    from app.services.importer import connect
    db = connect(path)
    db.executescript("""CREATE TABLE product_pages (url TEXT PRIMARY KEY, fetched_at TEXT, status TEXT, product_id TEXT,
        configuration_id TEXT, prices INTEGER, error TEXT, updated_at TEXT);
        CREATE TABLE product_specs (url TEXT PRIMARY KEY, spec_json TEXT);""")
    db.execute("INSERT INTO products(source_id) VALUES ('63')")
    db.execute("INSERT INTO configurations VALUES ('c1',1,'ES','EUR','public-web-no-session','{}','{}','test')")
    db.execute("INSERT INTO shipping_options(source_id) VALUES ('standard')")
    db.execute("INSERT INTO sync_runs(started_at,status,source,source_sha256) VALUES ('x','success','t','h')")
    for qid, value, net, total in ((1, 100, "11.13", "16.05"), (2, 1000, "50.00", "54.92")):
        db.execute("INSERT INTO quantities(id,product_id,source_id,value) VALUES (?,?,?,?)", (qid, 1, str(qid), value))
        db.execute("""INSERT INTO prices(configuration_id,quantity_id,shipping_option_id,product_net,total_net,total_gross,shipping_net,
            total_vat,unit_product_net,delivery_days,delivery_text,observed_at,imported_at,valid_until,run_id)
            VALUES ('c1',?,1,?,?,'0','4.92','0','0','5','Entrega','2026-10-27','2026-10-27','2026-11-27',1)""", (qid, net, total))
    url = "https://print24.com/es/productos-impresion/flyers"
    db.execute("INSERT INTO product_pages VALUES (?,?,?,?,?,?,?,?)", (url, "2026-10-27T12:00:00+00:00", "ok", "63", "c1", 2, None, "x"))
    db.execute("INSERT INTO product_specs VALUES (?,?)", (url, json.dumps([{"group": "Formato", "label": "105 x 148 mm DIN A6"}])))
    db.commit()
    db.close()


def test_print24_automatic_reference_prices(tmp_path):
    seed = tmp_path / "links.json"
    seed.write_text(json.dumps({"providers": {}}))
    make_catalog(tmp_path / "catalog.sqlite3")
    with TestClient(create_app(tmp_path / "work.sqlite3", seed, tmp_path / "catalog.sqlite3")) as client:
        r = client.post('/api/search', json={"brief": BRIEF}).json()
        p24 = next(p for p in r['providers'] if p['id'] == 'print24')
        assert p24['auto_matched'] == 1 and p24['auto'][0]['spec'][0]['label'].startswith("105 x 148")
        assert p24['auto'][0]['matches_quantity'] and p24['auto'][0]['suggested']['total_net'] == "54.92"
        assert p24['best'] is None and not r['winners']        # reference only: never ranked without a saved quote
        other = client.post('/api/search', json={"brief": {**BRIEF, "quantity": 500}}).json()
        auto = next(p for p in other['providers'] if p['id'] == 'print24')['auto'][0]
        assert auto['suggested'] is None and auto['quantities'] == [100, 1000]
        none = client.post('/api/search', json={"brief": {**BRIEF, "query": "camisetas"}}).json()
        assert next(p for p in none['providers'] if p['id'] == 'print24')['auto'] == []
        assert next(p for p in r['providers'] if p['id'] == 'truyol')['auto'] == []


def test_missing_catalog_is_not_an_error(tmp_path):
    seed = tmp_path / "links.json"
    seed.write_text(json.dumps({"providers": {}}))
    with TestClient(create_app(tmp_path / "w.sqlite3", seed, tmp_path / "nope.sqlite3")) as client:
        assert client.post('/api/search', json={"brief": BRIEF}).status_code == 200


def test_other_providers_reference_prices_total_and_unit(tmp_path):
    from app.collectors import offers as store
    seed = tmp_path / "links.json"
    seed.write_text(json.dumps({"providers": {}}))
    cat = tmp_path / "catalog.sqlite3"
    db = store.connect(cat)
    base = {"currency": "EUR", "tax": "net", "shipping": "included", "scope": "t"}
    store.replace_offers(db, "onlineprinters", "https://www.onlineprinters.es/p/flyers-a5", "Imprimir flyers A5",
                         [{**base, "quantity": 500, "kind": "total", "price": "36.61"}, {**base, "quantity": 1000, "kind": "total", "price": "42.80"}],
                         "2026-10-27", [{"group": "Formato", "label": "A5"}])
    store.replace_offers(db, "tuskamisetas", "https://www.tuskamisetas.com/es/producto/flyer-shirt", "Camiseta flyers",
                         [{**base, "tax": "unknown", "shipping": "excluded", "variant": "Blanco", "quantity": q, "kind": "unit", "price": p}
                          for q, p in ((1, "2.75"), (100, "1.98"), (500, "1.53"))], "2026-10-27")
    db.close()
    with TestClient(create_app(tmp_path / "work.sqlite3", seed, cat)) as client:
        r = client.post('/api/search', json={"brief": {**BRIEF, "quantity": 500}}).json()
        op = next(p for p in r['providers'] if p['id'] == 'onlineprinters')['auto'][0]
        assert op['price_kind'] == 'total' and op['suggested']['total_net'] == "36.61" and op['suggested']['delivery_days'] is None
        assert op['suggested']['meets_deadline'] is True and op['spec'] == [{"group": "Formato", "label": "A5"}]
        tk = next(p for p in r['providers'] if p['id'] == 'tuskamisetas')['auto'][0]
        assert tk['price_kind'] == 'unit' and tk['title'].endswith("Blanco") and tk['tax_status'] == 'unknown'
        assert tk['suggested']['quantity'] == 500 and Decimal(tk['suggested']['total_net']) == Decimal("765.00")
        odd = client.post('/api/search', json={"brief": {**BRIEF, "quantity": 250}}).json()
        assert next(p for p in odd['providers'] if p['id'] == 'tuskamisetas')['auto'][0]['suggested']['quantity'] == 100  # tier applies from 100
        assert next(p for p in odd['providers'] if p['id'] == 'onlineprinters')['auto'][0]['suggested'] is None  # totals only at published quantities
        assert all(p['best'] is None for p in r['providers']) and not r['winners']  # references never enter the ranking


def test_print24_variations_appear_next_to_the_default(tmp_path):
    from app.collectors import variants
    seed = tmp_path / "links.json"
    seed.write_text(json.dumps({"providers": {}}))
    cat = tmp_path / "catalog.sqlite3"
    make_catalog(cat)
    import sqlite3
    db = sqlite3.connect(cat)
    db.executescript(variants.SCHEMA)
    db.execute("INSERT INTO configurations VALUES ('c2',1,'ES','EUR','public-web-no-session','{}','{}','test')")
    db.execute("""INSERT INTO prices(configuration_id,quantity_id,shipping_option_id,product_net,total_net,total_gross,shipping_net,
        total_vat,unit_product_net,delivery_days,delivery_text,observed_at,imported_at,valid_until,run_id)
        VALUES ('c2',2,1,'60.00','64.92','0','4.92','0','0','5','Entrega','2026-10-27','2026-10-27','2026-11-27',1)""")
    db.execute("INSERT INTO config_specs VALUES ('c2','Papel: 135 g/m² Papel estucado',?)",
               (json.dumps([{"group": "Papel", "label": "135 g/m² Papel estucado"}]),))
    db.commit()
    db.close()
    with TestClient(create_app(tmp_path / "work.sqlite3", seed, cat)) as client:
        r = client.post('/api/search', json={"brief": {**BRIEF, "quantity": 1000}}).json()
        p24 = next(p for p in r['providers'] if p['id'] == 'print24')['auto']
        assert [a['title'] for a in p24] == ["Flyers", "Flyers · Papel: 135 g/m² Papel estucado"]
        assert p24[0]['suggested']['total_net'] == "54.92" and p24[1]['suggested']['total_net'] == "64.92"
        assert p24[1]['spec'][0]['label'].startswith("135 g/m²")


def test_catalog_lists_everything_with_filters_and_paging(tmp_path):
    from app.collectors import offers as store
    seed = tmp_path / "links.json"
    seed.write_text(json.dumps({"providers": {}}))
    cat = tmp_path / "catalog.sqlite3"
    make_catalog(cat)
    db = store.connect(cat)
    base = {"currency": "EUR", "tax": "net", "shipping": "included", "scope": "t"}
    for i in range(3):
        store.replace_offers(db, "onlineprinters", f"https://www.onlineprinters.es/p/flyer-{i}", f"Imprimir flyers {i}",
                             [{**base, "quantity": 100, "kind": "total", "price": f"{20 + i}.00"}, {**base, "quantity": 500, "kind": "total", "price": f"{30 + i}.00"}],
                             "2026-10-27", [{"group": "Formato", "label": "A5"}])
    db.close()
    with TestClient(create_app(tmp_path / "work.sqlite3", seed, cat)) as client:
        all_rows = client.get('/api/catalog').json()
        assert all_rows['total'] == 4 and all_rows['counts']['print24'] == 1 and all_rows['counts']['onlineprinters'] == 3
        assert [i['provider'] for i in all_rows['items']] == ['print24', 'onlineprinters', 'onlineprinters', 'onlineprinters']
        op = client.get('/api/catalog', params={"provider": "onlineprinters", "q": "flyers 1"}).json()
        assert op['total'] == 1 and op['items'][0]['from_price'] == "21.00" and (op['items'][0]['min_quantity'], op['items'][0]['max_quantity']) == (100, 500)
        page2 = client.get('/api/catalog', params={"limit": 2, "offset": 2}).json()
        assert page2['total'] == 4 and len(page2['items']) == 2
        assert client.get('/api/catalog', params={"provider": "nope"}).status_code == 422
        assert client.get('/api/catalog', params={"limit": 0}).status_code == 422
    with TestClient(create_app(tmp_path / "w2.sqlite3", seed, tmp_path / "missing.sqlite3")) as client:
        assert client.get('/api/catalog').json()['total'] == 0


def test_card_extras_validated(client):
    card = {**BRIEF, "query": "tarjetas de visita", "extras": {"type": "Exclusiva", "pages": "1 cara"}}
    assert client.post('/api/search', json={"brief": card}).status_code == 200
    assert client.post('/api/search', json={"brief": {**card, "extras": {"type": "Inventada"}}}).status_code == 422
    assert client.post('/api/search', json={"brief": {**card, "extras": {"colour": "Rojo"}}}).status_code == 422


def _entry(url, title, spec):
    from app.services.workbench import enrich_spec  # as the search does for Onlineprinters pages
    return {"url": url, "title": title, "spec": enrich_spec([{"group": g, "label": l} for g, l in spec], url)}


BASE = {"format": "Sin especificar", "material": "Sin especificar", "printing": "Sin especificar", "finishing": "Sin especificar", "extras": {}}
ONLINE = lambda: _entry("https://x.es/p/tarjetas-visita-4-4-90x50mm", "Tarjetas de visita",
                        [("Papel", "300 g/m² papel cuché PEFC Economy"), ("Realización", "cuché mate"), ("Acabados", "sin acabado")])
PRINT24 = lambda: _entry("https://print24.com/es/productos-impresion/tarjetas-de-visita", "Tarjetas de visita",
                         [("Páginas", "1 cara"), ("Formato", "85 x 55 mm"), ("Orientación", "Horizontal"),
                          ("Papel", "350 g/m² Papel estucado"), ("Impresión", "4+0 tintas (CMYK)"), ("Procesamiento", "Cortar"),
                          ("Acabados", "Sin"), ("Prueba", "Sin prueba")])


def test_entry_matches_filters_strictly():
    from app.services.cards import entry_matches
    card = ONLINE()
    assert entry_matches(card, BASE)
    assert entry_matches(card, {**BASE, "format": "90 x 50 mm"}) and entry_matches(card, {**BASE, "format": "9,0 x 5,0 cm"})
    assert not entry_matches(card, {**BASE, "format": "85 x 55 mm"})
    assert entry_matches(card, {**BASE, "material": "300 g/m² papel cuché PEFC Economy"})
    assert entry_matches(card, {**BASE, "material": "300 g/m² Papel estucado"})  # same grammage, cuché = estucado
    assert not entry_matches(card, {**BASE, "material": "350 g/m² Papel estucado"})
    assert entry_matches(card, {**BASE, "printing": "4+4 tintas (CMYK)"})
    assert not entry_matches(card, {**BASE, "printing": "4+0 tintas (CMYK)"})
    assert entry_matches(card, {**BASE, "finishing": "Sin"})
    assert not entry_matches(card, {**BASE, "finishing": "Plastificado"})  # 'cuché mate' is the paper, not a laminate
    assert entry_matches(card, {**BASE, "extras": {"type": "Estándar", "processing": "Cortar"}})
    assert not entry_matches(card, {**BASE, "extras": {"type": "Exclusiva"}})


def test_print24_card_matches_its_own_form_options():
    from app.services.cards import entry_matches
    page = PRINT24()
    full = {"format": "85 x 55 mm", "material": "350 g/m² Papel estucado", "printing": "4+0 tintas (CMYK)", "finishing": "Sin",
            "extras": {"pages": "1 cara", "orientation": "Horizontal", "processing": "Cortar", "proof": "Sin prueba"}}
    assert entry_matches(page, full, "print24")
    assert not entry_matches(page, {**full, "extras": {**full["extras"], "orientation": "Vertical"}}, "print24")
    assert not entry_matches(page, {**full, "extras": {"processing": "Cortar, redondear esquinas"}}, "print24")
    assert not entry_matches(page, {**full, "extras": {"proof": "Prueba en pantalla"}}, "print24")
    assert entry_matches(ONLINE(), {**BASE, "extras": {"proof": "Prueba en pantalla"}}, "onlineprinters")  # Print24-only question


def test_card_form_reads_print24_options_from_cache(tmp_path):
    from app.services.cards import card_form
    assert card_form(tmp_path / "missing.sqlite3")["paper"] == []
    real = Path(__file__).resolve().parents[1] / "data/catalog.sqlite3"
    if (real.parent / "cache/products/productos-impresion__tarjetas-de-visita.html").exists():
        form = card_form(real)
        assert "85 x 55 mm" in form["format"] and "Horizontal" in form["orientation"] and "Cortar" in form["processing"]


def test_strict_search_says_nothing_matches(client):
    brief = {**BRIEF, "query": "tarjetas de visita", "strict": True, "format": "12 x 3 mm"}
    result = client.post('/api/search', json={"brief": brief}).json()
    assert all(p["auto"] == [] for p in result["providers"])


def test_catalog_card_filter_keeps_only_matching_business_cards(tmp_path):
    from app.collectors import offers as store
    seed = tmp_path / "links.json"
    seed.write_text(json.dumps({"providers": {}}))
    cat = tmp_path / "catalog.sqlite3"
    make_catalog(cat)
    db = store.connect(cat)
    base = {"currency": "EUR", "tax": "net", "shipping": "included", "scope": "t"}
    for slug, name in (("tarjetas-visita-4-4-85x55mm", "Tarjetas de visita"), ("flyers-a5", "Flyers")):
        store.replace_offers(db, "onlineprinters", f"https://www.onlineprinters.es/{slug}", name,
                             [{**base, "quantity": 100, "kind": "total", "price": "20.00"}], "2026-10-27", [{"group": "Papel", "label": "350 g/m² Papel estucado"}])
    db.close()
    with TestClient(create_app(tmp_path / "work.sqlite3", seed, cat)) as client:
        def ask(**filters):
            body = {"format": "Sin especificar", "material": "Sin especificar", "printing": "Sin especificar", "finishing": "Sin especificar", "extras": {}, **filters}
            return client.get('/api/catalog', params={"cards": json.dumps(body)})
        assert [i['title'] for i in ask().json()['items'] if i['provider'] == 'onlineprinters'] == ['Tarjetas de visita']
        assert ask(format="85 × 55 mm").json()['total'] >= 1
        assert [i for i in ask(format="90 x 50 mm").json()['items'] if i['provider'] == 'onlineprinters'] == []
        assert client.get('/api/catalog', params={"cards": "no json"}).status_code == 422
        assert client.get('/api/catalog', params={"cards": json.dumps({"extras": {"raro": "x"}})}).status_code == 422


def test_card_form_adds_options_from_other_providers(tmp_path):
    from app.collectors import offers as store
    from app.services.cards import card_form
    cat = tmp_path / "catalog.sqlite3"
    make_catalog(cat)
    db = store.connect(cat)
    base = {"currency": "EUR", "tax": "net", "shipping": "included", "scope": "t"}
    store.replace_offers(db, "onlineprinters", "https://www.onlineprinters.es/p/tarjetas-visita-4-4-55x55mm", "Tarjetas de visita",
                         [{**base, "quantity": 75, "kind": "total", "price": "20.00"}], "2026-10-27", [{"group": "Papel", "label": "240 g/m² Rococo (Gmund) FSC mix"}])
    store.replace_offers(db, "onlineprinters", "https://www.onlineprinters.es/p/flyers-a5", "Flyers",
                         [{**base, "quantity": 33, "kind": "total", "price": "20.00"}], "2026-10-27", [{"group": "Papel", "label": "90 g/m² flyer"}])
    db.close()
    form = card_form(cat)
    assert "55 x 55 mm" in form["format"] and "4+4 tintas (CMYK)" in form["inks"]
    assert "240 g/m² Papel noble" in form["paper"] and not any("flyer" in x for x in form["paper"])
    assert "75 Unidades" in form["quantity"] and "33 Unidades" not in form["quantity"]


def _flyer_catalog(tmp_path):
    from app.collectors import offers as store
    cat = tmp_path / "catalog.sqlite3"
    make_catalog(cat)
    db = store.connect(cat)
    base = {"currency": "EUR", "tax": "net", "shipping": "included", "scope": "t"}
    for slug, size, paper in (("flyers-a5", "A5", "135 g/m² papel estucado"), ("flyers-a6", "A6", "170 g/m² papel estucado")):
        store.replace_offers(db, "onlineprinters", f"https://www.onlineprinters.es/p/{slug}", f"Flyers {size}",
                             [{**base, "quantity": 500, "kind": "total", "price": "30.00"}], "2026-10-27",
                             [{"group": "Formato", "label": size}, {"group": "Papel", "label": paper}])
    db.close()
    return cat


def test_product_form_lists_collected_options_and_filters(tmp_path):
    from app.services.products import generic_matches, product_form
    form = product_form(_flyer_catalog(tmp_path), "flyers")
    groups = {g["name"]: g["options"] for g in form["groups"]}
    assert "A5" in groups["Formato"] and sum("A6" in x for x in groups["Formato"]) == 1 and len(groups["Papel"]) == 2 and form["matched"] >= 2
    entry = {"spec": [{"group": "Formato", "label": "A5"}, {"group": "Material", "label": "135 g/m² Papel estucado"}]}
    assert generic_matches(entry, {"Formato": "A5", "Papel": "135 g/m² Papel estucado"})
    assert not generic_matches(entry, {"Formato": "A6"}) and not generic_matches(entry, {"Perforación": "Sí"})


def test_generic_strict_search_and_options_endpoint(tmp_path):
    seed = tmp_path / "links.json"
    seed.write_text(json.dumps({"providers": {}}))
    cat = _flyer_catalog(tmp_path)
    with TestClient(create_app(tmp_path / "work.sqlite3", seed, cat)) as client:
        assert {g["name"] for g in client.get('/api/product-options', params={"q": "flyers"}).json()["groups"]} >= {"Formato", "Papel"}
        assert client.get('/api/product-options', params={"q": "x"}).status_code == 422
        brief = {**BRIEF, "query": "flyers", "strict": True, "generic": True, "filters": {"Formato": "A6"}}
        found = {p["id"]: p["auto"] for p in client.post('/api/search', json={"brief": brief}).json()["providers"]}
        assert [e["url"].rsplit("/", 1)[-1] for e in found["onlineprinters"]] == ["flyers-a6"]
        brief["filters"] = {"Formato": "A3"}
        assert all(p["auto"] == [] for p in client.post('/api/search', json={"brief": brief}).json()["providers"])


def test_lan_mode_is_read_only_for_other_computers(tmp_path):
    seed = tmp_path / "links.json"
    seed.write_text(json.dumps({"providers": {}}))
    cat = tmp_path / "catalog.sqlite3"
    make_catalog(cat)
    other = TestClient(create_app(tmp_path / "w.sqlite3", seed, cat, lan=True), client=("192.168.1.50", 5000), base_url="http://192.168.1.10:8765")
    outside = TestClient(create_app(tmp_path / "w2.sqlite3", seed, cat, lan=True), client=("8.8.8.8", 5000), base_url="http://192.168.1.10:8765")
    local = TestClient(create_app(tmp_path / "w3.sqlite3", seed, cat), base_url="http://192.168.1.10:8765")
    assert other.get('/api/providers').status_code == 200
    assert other.post('/api/search', json={"brief": BRIEF}, headers={"origin": "http://192.168.1.10:8765"}).status_code == 200
    assert other.post('/api/quotes', json={}).status_code == 403 and "lectura" in other.post('/api/quotes', json={}).json()["detail"]
    assert outside.get('/api/providers').status_code == 403
    assert local.get('/api/providers').status_code == 400  # default mode still rejects other host names


def test_general_page_goes_first():
    from app.services.workbench import general_rank
    words = ["tarjetas", "de", "visita"]
    links = [{"url": "https://www.onlineprinters.es/p/muestras-de-tarjetas-de-visita"},
             {"url": "https://www.onlineprinters.es/k/tarjetas-visita-plegados-formato-horizontal"},
             {"url": "https://www.onlineprinters.es/k/tarjetas-visita"}]
    assert sorted(links, key=lambda l: general_rank(l, words))[0]["url"].endswith("/k/tarjetas-visita")


def test_search_words_ignore_little_words_and_plurals():
    from app.services.workbench import query_words, terms_for
    assert query_words("Tarjetas de Visita") == ["tarjetas", "visita"]
    assert "visita" in terms_for("visitas") and "flyer" in terms_for("folletos") and "cartel" in terms_for("carteles")
    assert "playera" in terms_for("camiseta")


def test_catalog_returns_general_page_and_suggestions(tmp_path):
    seed = tmp_path / "links.json"
    seed.write_text(json.dumps({"providers": {"onlineprinters": {"links": [
        {"title": "Tarjetas de visita plegables horizontal", "url": "https://www.onlineprinters.es/k/tarjetas-visita-plegables-horizontal"},
        {"title": "Tarjetas de visita", "url": "https://www.onlineprinters.es/k/tarjetas-visita"}]}}}))
    cat = tmp_path / "catalog.sqlite3"
    make_catalog(cat)
    with TestClient(create_app(tmp_path / "work.sqlite3", seed, cat)) as client:
        general = client.get('/api/catalog', params={"q": "tarjetas de visita"}).json()["general"]
        assert general["onlineprinters"]["url"].endswith("/k/tarjetas-visita") and general["stricker"] is None
        terms = {t["term"]: t["count"] for t in client.get('/api/suggestions').json()["terms"]}
        assert terms.get("tarjetas de visita", 0) >= 2


def test_catalog_words_understand_sizes_and_weights():
    from app.services.workbench import catalog_words
    assert catalog_words("85 x 55 mm 350 g/m2") == ["85x55", "350g"]
    assert catalog_words("tarjetas 8,5 x 5,5 cm") == ["tarjetas", "85x55"]
    assert catalog_words("flyer A5 135gr") == ["flyer", "a5", "135g"]


def test_compare_puts_providers_side_by_side_and_marks_cheapest():
    from app.services.compare import compare
    def item(provider, title, spec, prices, kind="total"):
        return {"provider": provider, "title": title, "url": f"https://{provider}.test/{title}", "spec": spec, "price_kind": kind, "prices": prices}
    base = [{"group": "Formato", "label": "85 x 55 mm"}, {"group": "Papel", "label": "350 g/m² papel estucado"}, {"group": "Páginas", "label": "1 cara"}]
    items = [item("print24", "a", base, [[500, "30.00"]]), item("onlineprinters", "b", base, [[500, "25.00"]]),
             item("printai", "c", base, [[100, "10.00"]]), item("truyol", "d", [], [[500, "5.00"]]),
             item("tuskamisetas", "e", base, [[500, "0.04"]], kind="unit")]
    out = compare(items, 500)
    row = out["rows"][0]
    assert row["label"] == "85 × 55 mm · 350 g/m² · 1 cara" and set(row["cells"]) == {"print24", "onlineprinters", "tuskamisetas"}
    assert row["cheapest"] == "tuskamisetas" and row["cells"]["tuskamisetas"]["estimated"] and out["skipped"] == 2
    assert row["cells"]["tuskamisetas"]["total"] == "20.00"
