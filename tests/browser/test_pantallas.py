from playwright.sync_api import expect
from axe_playwright_python.sync_playwright import Axe


def open_home(page):
    page.goto(f"{page.base}/")
    expect(page.locator("#tool-results .offer, #tool-results .empty-box").first).to_be_visible(timeout=15000)


def pressed(page, key, value):
    return page.locator(f'.pill[data-key="{key}"][data-value="{value}"]')


def test_sin_errores_ni_scroll_horizontal(page):
    open_home(page)
    assert page.errors == []
    ancho = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert ancho[0] <= ancho[1], f"scroll horizontal: {ancho}"


def test_contraste_wcag_aa(page):
    open_home(page)
    result = Axe().run(page, options={"runOnly": ["color-contrast"]})
    malos = [f"{n['target']} {n['failureSummary'].splitlines()[1] if n['failureSummary'] else ''}"
             for v in result.response["violations"] for n in v["nodes"]]
    assert not malos, "\n".join(malos[:8])


def test_todo_empieza_en_lo_estandar(page):
    open_home(page)
    for key, value in (("quantity", "100"), ("format", "85 x 55 mm"), ("pages", "1 cara"), ("grams", "350 g/m²"),
                       ("paper_type", "Estucado / cuché"), ("finishing", "Sin"), ("surface", ""), ("days", "0"), ("inks", "cmyk")):
        expect(pressed(page, key, value)).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#tool-summary")).to_contain_text("100 tarjetas")
    expect(page.locator("#tool-summary")).to_contain_text("85 × 55 mm")


def test_los_botones_cambian_el_precio(page):
    open_home(page)
    pressed(page, "quantity", "500").click()
    expect(page.locator("#tool-results")).to_contain_text("36,30")  # 30,00 € sin IVA × 1,21
    expect(pressed(page, "quantity", "500")).to_have_attribute("aria-pressed", "true")
    page.fill('input[data-key="quantity"]', "1000")
    page.press('input[data-key="quantity"]', "Enter")
    expect(page.locator("#tool-summary")).to_contain_text("1000 tarjetas")


def test_gramaje_distinto_sale_como_parecida_y_cualquiera_lo_quita(page):
    open_home(page)
    pressed(page, "quantity", "500").click()
    onlineprinters = page.locator(".offer", has_text="Onlineprinters")
    printai = page.locator(".offer", has_text="Printai")
    expect(onlineprinters).to_be_visible()
    expect(printai).to_contain_text("300 g (pediste 350 g)")  # su ficha es de 300 g
    pressed(page, "grams", "").click()
    expect(printai).not_to_contain_text("pediste")
    pressed(page, "surface", "Mate").click()  # ninguna ficha de prueba dice mate
    expect(page.locator("#tool-results .empty-box")).to_be_visible()


def test_pedido_de_cliente_rellena_los_botones(page):
    open_home(page)
    page.click("#customer-box summary")
    page.fill("#customer-text", "Necesito 500 tarjetas de visita de 85x55 mm en papel de 300 g por las dos caras")
    page.click("#customer-go")
    expect(page.locator("#tool-summary")).to_contain_text("He entendido")
    expect(pressed(page, "quantity", "500")).to_have_attribute("aria-pressed", "true")
    expect(pressed(page, "pages", "2 caras")).to_have_attribute("aria-pressed", "true")
    expect(pressed(page, "grams", "300 g/m²")).to_have_attribute("aria-pressed", "true")


def test_no_salen_proveedores_sin_productos(page):
    open_home(page)
    resultados = page.locator("#tool-results").inner_text()
    assert "Truyol" not in resultados and "Stricker" not in resultados
    toggles = page.locator("#provider-toggles").text_content()
    assert "Truyol" not in toggles and "Stricker" not in toggles
    assert "Onlineprinters" in toggles


def test_menu_visible_tras_scroll(page):
    open_home(page)
    page.mouse.wheel(0, 1500)
    page.wait_for_timeout(300)
    nav = page.locator(".sidebar").bounding_box()
    if page.size == "escritorio":
        assert nav and nav["x"] >= 0 and nav["y"] >= 0, "el menú lateral debe seguir visible"
    else:
        assert nav is not None  # en móvil basta con que exista y no tape la página


def test_anotar_un_precio_a_mano_y_borrarlo(page):
    open_home(page)
    printai = page.locator(".offer", has_text="Printai")
    expect(printai).to_contain_text("pediste")
    try:
        printai.get_by_text("Anotar el precio real").click()
        expect(page.locator("#manual-dialog")).to_be_visible()
        page.fill("#m-url", "https://www.printai.es/tarjetas-de-visita/")
        page.fill("#m-price", "16,63")
        page.click("#manual-save")
        expect(page.locator(".offer", has_text="Printai")).to_contain_text("Anotado a mano")
        expect(page.locator(".offer", has_text="Printai")).not_to_contain_text("pediste")
        expect(page.locator("#manual-count")).to_have_text("1")
        page.once("dialog", lambda d: d.accept())
        page.locator("#manual-box summary").click()
        page.locator(".manual-del").first.click()
        expect(page.locator("#manual-count")).to_have_text("0")
    finally:  # la base del servidor de pruebas se comparte entre casos
        for row in page.request.get(f"{page.base}/api/manual-prices").json()["items"]:
            page.request.post(f"{page.base}/api/manual-prices/delete", data={"id": row["id"]})


def test_el_buscador_da_la_misma_pantalla_para_cualquier_producto(page):
    open_home(page)
    expect(page.locator("#cat-q")).to_be_visible()
    page.fill("#cat-q", "flyers")
    expect(page.locator("#tool-title")).to_contain_text("flyers")
    expect(page.locator("#tool-results .offer").first).to_be_visible()
    formato = page.locator('.pill[data-key="g:Formato"][data-value]:not([data-value=""])').first
    expect(formato).to_be_visible()  # las opciones salen de lo que dicen las fichas recogidas
    value = formato.get_attribute("data-value")
    formato.click()
    expect(page.locator("#tool-summary")).to_contain_text(value)
    pressed(page, "quantity", "500").click()
    expect(page.locator("#tool-summary")).to_contain_text("500 uds")
    page.fill("#cat-q", "")
    expect(page.locator("#tool-title")).to_have_text("Tarjetas de visita")
    expect(pressed(page, "format", "85 x 55 mm")).to_have_attribute("aria-pressed", "true")
    page.fill("#cat-q", "flyers")
    page.click("#customer-box summary")
    page.fill("#customer-text", "Necesito 500 tarjetas de visita")
    page.click("#customer-go")  # un pedido de tarjetas vuelve a la pantalla guiada
    expect(page.locator("#tool-title")).to_have_text("Tarjetas de visita")
    expect(page.locator("#cat-q")).to_have_value("")


def test_editar_un_precio_anotado_sin_duplicarlo(page):
    open_home(page)
    printai = page.locator(".offer", has_text="Printai")
    try:
        printai.get_by_text("Anotar el precio real").click()
        page.fill("#m-url", "https://www.printai.es/tarjetas-de-visita/")
        page.fill("#m-price", "16,63")
        page.click("#manual-save")
        expect(page.locator("#manual-count")).to_have_text("1")
        page.locator("#manual-box summary").click()
        page.locator(".manual-edit").first.click()
        expect(page.locator("#manual-heading")).to_have_text("Editar el precio anotado")
        expect(page.locator("#m-price")).to_have_value("16,63")
        page.fill("#m-price", "19,90")
        page.click("#manual-save")
        expect(page.locator("#manual-body")).to_contain_text("19,90")
        expect(page.locator("#manual-count")).to_have_text("1")  # cambiado, no duplicado
    finally:
        for row in page.request.get(f"{page.base}/api/manual-prices").json()["items"]:
            page.request.post(f"{page.base}/api/manual-prices/delete", data={"id": row["id"]})


def test_anotar_varias_cantidades_de_golpe(page):
    open_home(page)
    lines = "['100 = 16,63', '1.000 = 48,50', '10.000: 300'].join(String.fromCharCode(10))"
    assert page.evaluate(f"parseMany({lines})") == [
        {"quantity": 100, "price": "16.63"}, {"quantity": 1000, "price": "48.50"}, {"quantity": 10000, "price": "300"}]
    printai = page.locator(".offer", has_text="Printai")
    try:
        printai.get_by_text("Anotar el precio real").click()
        page.fill("#m-url", "https://www.printai.es/tarjetas-de-visita/")
        page.fill("#m-many", "100 = 16,63\n1.000 = 48,50\n10.000 = 300")
        page.click("#manual-save")  # quantity and price boxes are not needed when the list is filled
        expect(page.locator("#manual-count")).to_have_text("3")
        expect(page.locator(".offer", has_text="Printai")).to_contain_text("Anotado a mano")
    finally:
        for row in page.request.get(f"{page.base}/api/manual-prices").json()["items"]:
            page.request.post(f"{page.base}/api/manual-prices/delete", data={"id": row["id"]})
