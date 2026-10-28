# CLAUDE.md — API (comparador de imprentas)

Recoge precios públicos de imprentas (Print24, Onlineprinters, Printai, TusKamisetas; Truyol y Stricker pendientes) en una SQLite local y los muestra en una web local para ver dónde sale más barato un trabajo. WooCommerce queda para después.

## Stack
- Python 3.12 (venv con `uv`), FastAPI + Uvicorn, SQLite, pytest. Web estática (`web/`) sin framework.

## Arquitectura
- `app/collectors/`: `discovery.py` (robots + sitemap + portada), `sitemaps.py` (URLs de catálogo Print24), `products.py` (fichas Print24 → matriz de precios), `specs.py` (etiquetas legibles, offline), `tuskamisetas.py`, `onlineprinters.py`, `printai.py`, `offers.py` (tabla común `supplier_offers`), `index_homepages.py` (índice de enlaces de los 6 proveedores), `variants.py` (variaciones de una opción cada vez de Print24; navegador; SIN PROBAR en la web real).
- `app/parsers/`: `price_matrix.py` (formato real de Print24), `product_page.py` (extrae `calculationData` de Next.js).
- `app/services/`: `cards.py` (formulario y filtros de tarjetas de visita), `importer.py` (importación atómica con historial), `workbench.py` (búsqueda, presupuestos manuales, precios de referencia).
- `app/api/web.py` + `web/`: comparador en http://127.0.0.1:8765.
- Datos: `data/catalog.sqlite3` (Print24: `prices`, `product_pages`, `product_specs`, `catalog_urls`; resto: `supplier_offers`, `supplier_pages`), `data/cache/<proveedor>/` (HTML crudo), `data/workbench.sqlite3` (presupuestos manuales).
- Web: búsqueda con precios de referencia (`/api/search`) y «Catálogo completo» (`/api/catalog`, todo lo recogido con filtro por proveedor y texto, paginado).
- Flujo: recolector → caché en disco → SQLite → web (referencia) → el usuario confirma equivalencia con «Usar» → presupuesto → ranking.

## Comandos
- Tests: `.\.venv\Scripts\python.exe -m pytest -q --basetemp .test-runs/N` (N nuevo cada vez).
- Web: `Abrir comparador.cmd` o `python web_server.py --open`.
- Print24: `python -m app.collectors.sitemaps`, luego `python -m app.collectors.products` (171 productos, ~15 min), luego `python -m app.collectors.specs`.
- Otros: `python -m app.collectors.<tuskamisetas|onlineprinters|printai> URL…`; Onlineprinters entero: `python -m app.collectors.onlineprinters` (usa el sitemap en caché).
- Variaciones Print24 (navegador, entorno aparte `.venv-browser` con scrapling+playwright+Chromium, 719 MB en `%LOCALAPPDATA%\ms-playwright`): `.venv-browser\Scripts\python.exe -m app.collectors.variants --max-variations 3 URL`.
- Traslado a otro PC y recogida larga: ver `docs/MIGRACION.md` (`preparar_pc_nuevo.cmd`, `reanudar_recogida.cmd`, `estado_recogida.cmd`, `parar_recogida.cmd`, `empaquetar_para_otro_pc.cmd`; `python -m app.collectors.status`).
- Dependencias de tests: `requirements.txt` + `requirements-web.txt`.

## Reglas de recogida (obligatorias)
- Comprobar robots.txt, 5 s entre peticiones, sin redirecciones (se usa la URL canónica), sin cookies/login, caché 30 días. Un bloqueo, captcha real o error HTTP detiene todo; una ficha ilegible se anota y se salta.
- Nunca llamar a rutas que robots.txt prohíba (Printai `price_calculate.php`; Onlineprinters `tpl_productConfigurationJson`). No desactivar la verificación TLS.
- Autorización de scraping declarada por el usuario el 2026-10-27 para los 6 proveedores.
- Antes de ampliar de 3 productos de prueba a todo el catálogo de un proveedor, enseñar resultados y esperar confirmación.

## Decisiones
- 2026-10-27: el «Catálogo completo» también tiene el modo «Tarjetas de visita (con filtros)»: mismo formulario (`/api/card-options`), enviado como JSON en `/api/catalog?cards=…` y filtrado con `entry_matches`.
- 2026-10-27: el alcance de recogida pasa a «tarjetas de visita» (catálogo completo en pausa). Al buscar tarjetas, el formulario copia el configurador de Print24 (opciones leídas de su ficha en caché, `app/services/cards.py`) y filtra de verdad (`brief.strict`): solo salen fichas que cumplen todo; si no hay, la web lo dice. Prueba/individualización/diseños/empaquetado solo se piden a Print24. De Print24 solo hay precio de la configuración por defecto de cada ficha.
- 2026-10-27: los precios de los proveedores distintos de Print24 van a una tabla común `supplier_offers` (`price_kind` unit|total, `tax_status`, `shipping`); nada se asume si la página no lo dice.
- 2026-10-27: los precios automáticos son solo referencia: no entran en el ranking de «más barato» hasta que el usuario confirma equivalencia («Usar» → presupuesto).
- 2026-10-27: solo se recoge la configuración por defecto de cada producto (cobertura elegida por el usuario). Print24 trae opciones y matriz en el HTML (Next.js), sin llamar a su API.
- 2026-10-27: TusKamisetas tiene 15.593 productos (≈21 h a 5 s): no se lanza entero sin acotar categorías. Onlineprinters 1.907 (≈2,7 h). Printai ~1.011 URLs multi-idioma.
- 2026-10-27: Stricker no publica precios sin cuenta de revendedor; Truyol falla por un certificado autofirmado en su cadena TLS.
- 2026-10-27: el comparador web es el objetivo principal; WooCommerce es posterior.

- 2026-10-27: Print24 devuelve cuerpo vacío a clientes no navegador (price-matrix y token, también con la selección por defecto exacta); no se evade. `variants.py` usa Chromium normal (sin sigilo) y pide la selección por defecto como canario: si responde vacío, para. Scrapling 0.5 solo ofrece navegador en modo sigilo, por eso se usa Playwright directo.
- 2026-10-27: Onlineprinters: una ficha redirigida a la portada es un producto retirado (se anota y se sigue); 5 redirecciones seguidas lanzan una comprobación de una página que sí funcionaba y, si falla, paran.

## Patrones reutilizables
- **fetch_cached**: descarga con pausa, sin redirecciones y caché en disco, `app/collectors/sitemaps.py`.
- **offers.replace_offers**: sustituye atómicamente los precios de una ficha, `app/collectors/offers.py`.
- **calculation_data**: extrae el JSON del configurador de una página Next.js, `app/parsers/product_page.py`.

## Última actualización

2026-10-27
