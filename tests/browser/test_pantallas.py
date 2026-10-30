import re
import pytest
from playwright.sync_api import expect
from axe_playwright_python.sync_playwright import Axe


def open_home(page, q=""):
    page.goto(f"{page.base}/" + (f"?q={q}" if q else ""))
    page.wait_for_selector("#cat-table table, #cat-table .row, #cat-table tr", timeout=10000)


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


def test_buscar_tarjetas_muestra_precios(page):
    open_home(page)
    page.fill("#cat-q", "tarjetas de visita")
    page.click("#cat-go")
    expect(page.locator("#cat-table")).to_contain_text("Tarjetas")
    assert "30" in page.inner_text("#cat-table")


def test_pedido_de_cliente(page):
    open_home(page)
    page.fill("#customer-text", "Necesito 500 tarjetas de visita de 85x55 mm")
    page.click("#customer-go")
    expect(page.locator("#customer-items")).not_to_contain_text("Leyendo")
    expect(page.locator("#customer-items")).not_to_have_text("")
    assert "500" in page.inner_text("#customer-items")


def test_menu_visible_tras_scroll(page):
    open_home(page)
    page.mouse.wheel(0, 1500)
    page.wait_for_timeout(300)
    nav = page.locator(".sidebar").bounding_box()
    if page.size == "escritorio":
        assert nav and nav["x"] >= 0 and nav["y"] >= 0, "el menú lateral debe seguir visible"
    else:
        assert nav is not None  # en móvil basta con que exista y no tape la página
