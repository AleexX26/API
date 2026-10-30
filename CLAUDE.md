# CLAUDE.md — API (comparador de imprentas)

Recoge precios públicos de imprentas (Print24, Onlineprinters, Printai, TusKamisetas; Truyol y Stricker pendientes) en una SQLite local y los muestra en una web local para ver dónde sale más barato un trabajo. WooCommerce queda para después.

## Stack
- Python 3.12 (venv con `uv`), FastAPI + Uvicorn, SQLite, pytest. Web estática (`web/`) sin framework.

## Estructura de carpetas
- Raíz (solo lo de uso diario): `Abrir comparador.cmd`, `Abrir comparador para la oficina.cmd`, `web_server.py`, `main.py` (CLI antigua del importador), `README.md`, `CLAUDE.md`, `pyproject.toml`, `requirements*.txt`.
- `app/` código · `web/` interfaz · `tests/` pruebas · `docs/` documentación · `config/` · `herramientas/` instalar, recoger y trasladar (scripts `.cmd`/`.bat`) · `data/` datos y caché (no va a Git; ver `data/README.md`) · `dist/` ZIP para otros PC (no va a Git).

## Arquitectura
- `app/collectors/`: `discovery.py` (robots + sitemap + portada), `sitemaps.py` (URLs de catálogo Print24), `products.py` (fichas Print24 → matriz de precios), `specs.py` (etiquetas legibles, offline), `tuskamisetas.py`, `onlineprinters.py`, `printai.py`, `offers.py` (tabla común `supplier_offers`), `index_homepages.py` (índice de enlaces de los 6 proveedores), `variants.py` (variaciones de una opción cada vez de Print24; navegador; SIN PROBAR en la web real).
- `app/parsers/`: `price_matrix.py` (formato real de Print24), `product_page.py` (extrae `calculationData` de Next.js).
- `app/services/`: `cards.py` (formulario y filtros de tarjetas de visita), `products.py` (formulario de características de cualquier producto), `importer.py` (importación atómica con historial), `workbench.py` (búsqueda, presupuestos manuales, precios de referencia).
- `app/api/web.py` + `web/`: comparador en http://127.0.0.1:8765.
- Datos: `data/catalog.sqlite3` (Print24: `prices`, `product_pages`, `product_specs`, `catalog_urls`; resto: `supplier_offers`, `supplier_pages`), `data/cache/<proveedor>/` (HTML crudo), `data/workbench.sqlite3` (presupuestos manuales).
- Web: búsqueda con precios de referencia (`/api/search`) y «Catálogo completo» (`/api/catalog`, todo lo recogido con filtro por proveedor y texto, paginado).
- Flujo: recolector → caché en disco → SQLite → web (referencia) → el usuario confirma equivalencia con «Usar» → presupuesto → ranking.

## Comandos
- Tests: `.\.venv\Scripts\python.exe -m pytest -q --basetemp .test-runs/N` (N nuevo cada vez).
- Pruebas de navegador (`tests/browser/`, 20 casos: móvil 375 px y escritorio 1440 px, claro y oscuro; sin errores de consola, sin scroll horizontal, contraste WCAG AA con axe-core, búsqueda y pedido de cliente): necesitan `uv pip install --python .venv\Scripts\python.exe -r requirements-test.txt` y el Chromium de `%LOCALAPPDATA%\ms-playwright`; si faltan, se saltan solas.
- Web: `Abrir comparador.cmd` o `python web_server.py --open`. Para compartirlo con la misma red (solo lectura para los demás PC; solo el PC anfitrión guarda presupuestos): `Abrir comparador para la oficina.cmd` (`--lan`, escucha en 0.0.0.0:8765, muestra el enlace con la IP; Windows pide permiso de Firewall en redes privadas).
- Print24: `python -m app.collectors.sitemaps`, luego `python -m app.collectors.products` (171 productos, ~15 min), luego `python -m app.collectors.specs`.
- Otros: `python -m app.collectors.<tuskamisetas|onlineprinters|printai> URL…`; Onlineprinters entero: `python -m app.collectors.onlineprinters` (usa el sitemap en caché).
- Variaciones Print24 (navegador, entorno aparte `.venv-browser` con scrapling+playwright+Chromium, 719 MB en `%LOCALAPPDATA%\ms-playwright`): `.venv-browser\Scripts\python.exe -m app.collectors.variants --max-variations 3 URL`.
- PC nuevo de cero (instala Git, Python, clona el repo, descomprime los datos y prepara el entorno): copiar solo `herramientas/instalar_todo.bat` (y `API-datos.zip`) y hacer doble clic.
- Recoger datos / traslado entre PC (todo en `herramientas/`, ver `herramientas/LEEME.md` y `docs/MIGRACION.md`): `recogida/reanudar_recogida.cmd`, `recogida/recoger_print24.cmd`, `recogida/estado_recogida.cmd`, `recogida/parar_recogida.cmd`, `preparar_pc_nuevo.cmd`, `empaquetar_para_otro_pc.cmd`; estado por consola: `python -m app.collectors.status`.
- Dependencias de tests: `requirements.txt` + `requirements-web.txt`.

## Reglas de recogida (obligatorias)
- Comprobar robots.txt, 5 s entre peticiones, sin redirecciones (se usa la URL canónica), sin cookies/login, caché 30 días. Un bloqueo, captcha real o error HTTP detiene todo; una ficha ilegible se anota y se salta.
- Nunca llamar a rutas que robots.txt prohíba (Printai `price_calculate.php`; Onlineprinters `tpl_productConfigurationJson`). No desactivar la verificación TLS.
- Autorización de scraping declarada por el usuario el 2026-10-27 para los 6 proveedores.
- Antes de ampliar de 3 productos de prueba a todo el catálogo de un proveedor, enseñar resultados y esperar confirmación.

## Decisiones

- 2026-10-30: pruebas de navegador con Playwright en `tests/browser/` (servidor propio con catálogo mínimo; usa el puerto 8765 y, si está ocupado, modo red local en otro, porque las escrituras solo aceptan ese origen). Con ellas se oscurecieron los grises de `web/style.css` que no llegaban a contraste 4,5:1. La web no tiene tema oscuro propio: el caso «oscuro» solo comprueba que no se rompe con esa preferencia del sistema. Las fixtures no se pueden esperar con `wait_for_function(texto)` por la CSP (sin `unsafe-eval`): usar `expect(locator)`.
- 2026-10-30: la comparación es honesta: filas «idénticas» (mismo tamaño, gramaje, familia de papel, acabado y caras) y filas «parecidas» (mismo tamaño, gramaje y caras pero papel o acabado distinto, con el detalle de cada una); lo no comparable (`comparable:false`, p. ej. ropa sin personalizar de TusKamisetas) queda fuera y se avisa. Cada precio dice si el envío va incluido (`shipping`). Si la cantidad está entre dos tramos se estima con el precio por unidad de los vecinos y se marca «estimado entre N y M uds» (nunca fuera del rango). Lógica en `app/services/compare.py` (`price_at`, `compare`).

- 2026-10-30: carpeta ordenada: los scripts de instalar/recoger/trasladar pasan de la raíz a `herramientas/` (y `herramientas/recogida/`), y los registros y pruebas sueltos de `data/` a `data/registros/anteriores/` y `data/pruebas/`. Los `.cmd` se colocan solos en la carpeta del proyecto (`cd /d "%~dp0.."`). En la raíz solo quedan los dos «Abrir comparador».
- 2026-10-27: el «Catálogo completo» también tiene el modo «Tarjetas de visita (con filtros)»: mismo formulario (`/api/card-options`), enviado como JSON en `/api/catalog?cards=…` y filtrado con `entry_matches`.
- 2026-10-27: el alcance de recogida pasa a «tarjetas de visita» (catálogo completo en pausa). Al buscar tarjetas, el formulario copia el configurador de Print24 (opciones leídas de su ficha en caché, `app/services/cards.py`) y filtra de verdad (`brief.strict`): solo salen fichas que cumplen todo; si no hay, la web lo dice. Prueba/individualización/diseños/empaquetado solo se piden a Print24. De Print24 solo hay precio de la configuración por defecto de cada ficha.
- 2026-10-27: los precios de los proveedores distintos de Print24 van a una tabla común `supplier_offers` (`price_kind` unit|total, `tax_status`, `shipping`); nada se asume si la página no lo dice.
- 2026-10-27: los precios automáticos son solo referencia: no entran en el ranking de «más barato» hasta que el usuario confirma equivalencia («Usar» → presupuesto).
- 2026-10-27: solo se recoge la configuración por defecto de cada producto (cobertura elegida por el usuario). Print24 trae opciones y matriz en el HTML (Next.js), sin llamar a su API.
- 2026-10-27: TusKamisetas tiene 15.593 productos (≈21 h a 5 s): no se lanza entero sin acotar categorías. Onlineprinters 1.907 (≈2,7 h). Printai ~1.011 URLs multi-idioma.
- 2026-10-29: caja «Tengo el pedido de un cliente» en el catálogo: se pega el texto de la clienta y `app/services/request_parser.py` (reglas, sin servicio externo: el texto no sale del PC) saca producto, cantidad, tamaño, gramaje, caras, plazo y acabados; rellena la búsqueda y el catálogo enseña la comparación con «Lo más barato para este pedido». Endpoint `POST /api/parse-request`; `sides` filtra por una/dos caras. El acabado se muestra pero no se usa para buscar (las fichas casi nunca lo nombran). Varios productos en un texto = varios botones.
- 2026-10-29: el catálogo ordena (más barato / formato / nombre), filtra por entrega máxima (`days_at` en `compare.py`; Print24 trae días por opción, el resto se lee de «Plazo de producción» con `spec_days`; sin plazo escrito no pasa el filtro), lista como solo enlace las páginas sin precio (`unpriced_pages`: índice de enlaces + páginas fallidas que existen), avisa de datos de más de 30 días, guarda tus últimas búsquedas en el navegador (`mesa.recent`) y tiene una sección «Estado de los datos» (`/api/data-status`, `collectors/status.py: table`).
- 2026-10-28: los precios se muestran CON IVA 21% (`IVA` en `workbench.py` y `IVA` en `app.js`): los leídos como netos (Print24, Onlineprinters, Printai) se multiplican por 1,21 y se enseña también el neto; los de TusKamisetas (IVA desconocido) salen tal cual con «⚠ IVA sin confirmar» y nunca se marcan como más baratos. Los presupuestos manuales siguen en neto.
- 2026-10-28: el catálogo tiene casilla «Cantidad» (precio a esa cantidad con los tramos de cada ficha), tabla «Comparación» lado a lado (`app/services/compare.py`: mismo formato + gramaje + caras, un precio por proveedor, más barato marcado; orientativo) y busca por características (`85x55`, `a5`, `350 g` se entienden; `catalog_words`). Los desplegables de productos ocultan grupos sin valor (`HIDDEN_GROUPS` en `products.py`) y unen nombres (`ALIASES`, `PREFIX_ALIASES`). `fetch_cached` codifica acentos en las URLs (piñata).
- 2026-10-28: el catálogo es el buscador principal para los compañeros: caja de búsqueda con resultado al escribir, sugerencias (`/api/suggestions`), un bloque por proveedor con botón a su página general (`general` en `/api/catalog`, del índice de enlaces; si no hay, a la web del proveedor) y «Ver más», singular/plural y sinónimos (`terms_for`), y enlace compartible (`?q=…&p=…`).
- 2026-10-28: la web abre con el «Catálogo completo» arriba (sin columna «Leído»); en la búsqueda cada proveedor muestra una sola ficha (la de formato más grande) y el resto bajo «Ver más (N)».
- 2026-10-28: formulario de características para CUALQUIER producto (flyers, bolsas, camisetas…): `app/services/products.py` construye los desplegables a partir de las fichas recogidas que casan con la búsqueda (grupos unificados entre proveedores: Formato, Papel, Impresión…; A5 = DIN A5 = 148 x 210 mm) más todas las opciones del configurador de Print24 si su ficha está en caché. Endpoint `/api/product-options?q=`; la búsqueda manda `generic:true` + `filters` y solo salen fichas que indican lo elegido. Tarjetas de visita conserva su formulario propio (`cards.py`).
- 2026-10-28: las opciones del formulario de tarjetas ya no son solo de Print24: `card_form` suma formatos, papeles, tintas y cantidades de las tarjetas recogidas de los demás proveedores (`add_other_providers` en `cards.py`), sin duplicar (mismo formato/gramaje+familia/tintas). Prueba, individualización, diseños y empaquetado siguen siendo solo de Print24.
- 2026-10-28: Truyol no estaba bloqueado: el error TLS era que Python no conoce la raíz de Sectigo. `fetch_cached` usa ahora la lista de `certifi` (la verificación sigue activa). Su robots.txt solo prohíbe `/files/` y `*.pdf`. Cada ficha trae opciones (cantidad, formato, papel, caras, plastificado) y un único precio estático en JSON-LD; el precio por cantidad lo calcula su JavaScript (aún sin estudiar).
- 2026-10-27: Stricker no publica precios sin cuenta de revendedor; Truyol falla por un certificado autofirmado en su cadena TLS.
- 2026-10-27: el comparador web es el objetivo principal; WooCommerce es posterior.

- 2026-10-27: Print24 devuelve cuerpo vacío a clientes no navegador (price-matrix y token, también con la selección por defecto exacta); no se evade. `variants.py` usa Chromium normal (sin sigilo) y pide la selección por defecto como canario: si responde vacío, para. Scrapling 0.5 solo ofrece navegador en modo sigilo, por eso se usa Playwright directo.
- 2026-10-27: Onlineprinters: una ficha redirigida a la portada es un producto retirado (se anota y se sigue); 5 redirecciones seguidas lanzan una comprobación de una página que sí funcionaba y, si falla, paran.

## Patrones reutilizables
- **fetch_cached**: descarga con pausa, sin redirecciones y caché en disco, `app/collectors/sitemaps.py`.
- **offers.replace_offers**: sustituye atómicamente los precios de una ficha, `app/collectors/offers.py`.
- **calculation_data**: extrae el JSON del configurador de una página Next.js, `app/parsers/product_page.py`.

## Última actualización

2026-10-30
