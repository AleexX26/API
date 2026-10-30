# Print24 importer — prototipo local

El objetivo se ha ampliado a un comparador interno entre seis proveedores. Inventario,
fuentes y requisitos en [[docs/proveedores]]. El código de importación sigue siendo
monoproveedor Print24; la comparación entre imprentas todavía no está implementada.

Prototipo de importación local y descubrimiento web limitado. El usuario confirmó
autorización de scraping el 27-10-2026. Todavía no contiene un catálogo de precios
reales ni una integración completa. Investigación en
[[docs/investigacion_api]] y diseño en [[docs/arquitectura]].
Resultados iniciales y posteriores en [[docs/validacion]].

## Descubrimiento web autorizado

```powershell
.\.venv\Scripts\python.exe -m app.collectors.discovery data/nueva-prueba
```

Requiere salida a Internet y una carpeta de salida nueva. Consulta solamente robots.txt,
el sitemap español anunciado y la portada, con 5 segundos entre solicitudes. Guarda
respuestas y un manifiesto con URLs, estado y hashes. No sigue enlaces recursivamente,
no reutiliza cookies y no consulta APIs. Se detiene ante errores, redirecciones,
reglas incompatibles o indicios de bloqueo. Los 5 segundos son una precaución local,
no un límite publicado por Print24. No hay caché de reutilización entre ejecuciones.

La primera prueba real está en `data/discovery-20261027-01/manifest.json`: 9 sitemaps
y 48 enlaces de portada. Son candidatos, no productos confirmados. Los nombres de
los sitemaps distinguen categorías, productos y variantes; aún no se han descargado
esos documentos secundarios.

## Sitemaps de catálogo

```powershell
.\.venv\Scripts\python.exe -m app.collectors.sitemaps
```

Descarga `sitemap_category.xml`, `sitemap_product.xml` y `sitemap_productvariant.xml`
(comprobando antes `robots.txt` con la copia del descubrimiento), con 5 s entre peticiones,
sin redirecciones ni reintentos. El XML se guarda en `data/cache/sitemaps/` y no se vuelve
a pedir durante 30 días. Las URLs van a `catalog_urls` en `data/catalog.sqlite3`
(base nueva, separada de `demo.sqlite3`). Primer resultado, 27-10-2026: 13 categorías,
171 productos y 113 variantes. Son URLs, no precios ni configuraciones verificadas.

## Productos (configuración por defecto)

```powershell
.\.venv\Scripts\python.exe -m app.collectors.products --limit 3
.\.venv\Scripts\python.exe -m app.collectors.products URL1 URL2   # URLs concretas
```

Lee las URLs de producto de `catalog_urls`, descarga cada ficha (5 s entre peticiones, sin redirecciones,
caché en `data/cache/products/`) e importa sus precios con el parser de fichas. Un fallo HTTP o un posible
captcha detiene todo; una ficha que no se pueda interpretar se anota en `product_pages` y se salta.
Prueba del 27-10-2026 con 3 productos (flyers, tarjetas de visita, cajas plegables): 15 + 15 + 5 precios.
Aún no se ha lanzado el catálogo completo (171 productos).

## Web local (comparador)

`Abrir comparador.cmd` (o `python web_server.py --open`) la abre en http://127.0.0.1:8765. Lee de
`data/catalog.sqlite3` (cambiable con `PRINT_CATALOG_DB`): si Print24 tiene el producto buscado, muestra su tarifa
pública por defecto como **referencia** con las etiquetas de la configuración (formato, papel, tintas…). El botón
«Usar como presupuesto» rellena el formulario (solo si hay precio para la cantidad y plazo pedidos); tú confirmas la
equivalencia y lo guardas. Nada automático entra en el ranking sin ese paso. Antes hay que ejecutar, una vez
terminada la recogida, `python -m app.collectors.specs` para generar las etiquetas (sin red).

## TusKamisetas (precio por tramos)

```powershell
.\.venv\Scripts\python.exe -m app.collectors.tuskamisetas URL1 URL2 URL3
```

Lee la tabla «PRECIO POR CANTIDADES» de cada ficha `/es/producto/…` (precio por unidad **sin personalizar**, por
tramo de cantidad y variante Blanco/Color), con las mismas reglas que Print24 (robots.txt, 5 s, caché en
`data/cache/tuskamisetas/`, sin redirecciones). Guarda en `supplier_price_tiers`; `tax_status` queda en `unknown`
porque la página no dice si incluye IVA. Comprueba cada tabla contra el mínimo y máximo del `ld+json` de la página.
Detalles aprendidos: las cabeceras pueden ser `1000` o `+1000`, hay columnas repetidas con el mismo precio y los
productos baratos usan 3 decimales. Las URLs deben ir en minúsculas (la web redirige 301 a la canónica).
Probado el 27-10-2026 con 3 productos (camiseta E150, bolsa mochila, camiseta running): 40 tramos.

## Variaciones de Print24 (sin probar)

`python -m app.collectors.variants` (con `.venv-browser`) abre un Chromium normal, carga la ficha y pide a la propia
página el precio de la configuración por defecto (canario) y de cada alternativa cambiando UNA opción cada vez.
Si el canario vuelve vacío, para. Las variaciones válidas se importan y la web las muestra junto a la configuración por
defecto. **Todavía no se ha ejecutado contra la web real**: solo están probadas con datos de prueba las partes que no
usan el navegador.

## Ejecutar (Python 3.11+)

Para los tests hacen falta también las dependencias de `requirements-web.txt`.

Desde esta carpeta, en PowerShell:

```powershell
python -m venv .venv
uv --cache-dir .uv-cache pip install --python .venv/Scripts/python.exe -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe main.py --db data/pruebas/demo.sqlite3 init-db
.\.venv\Scripts\python.exe main.py --db data/pruebas/demo.sqlite3 import-matrix tests/fixtures/price_matrix.synthetic.json tests/fixtures/context.synthetic.json
.\.venv\Scripts\python.exe main.py --db data/pruebas/demo.sqlite3 status
.\.venv\Scripts\python.exe main.py --db data/pruebas/demo.sqlite3 export data/pruebas/exports/demo.json
.\.venv\Scripts\python.exe main.py --db data/pruebas/demo.sqlite3 export data/pruebas/exports/demo.csv --format csv
```

Si `python` apunta al alias de Microsoft Store, usar la ruta del intérprete instalado.
Alternativa a uv tras crear venv: `.venv/Scripts/python.exe -m pip install -r requirements.txt`.
Las exportaciones se crean exclusivamente: elegir otro nombre si ya existen.

## Formatos y límites

`price_matrix.synthetic.json` es una respuesta simulada con valores e identificadores
de prueba. `context.synthetic.json` es nuestro contexto obligatorio de importación:
producto, propiedades, país, moneda, ámbito de cuenta, servicios, evidencia y fechas
con zona horaria. No es un payload oficial. No inferir EUR ni vigencia de un mes para
datos reales: deben proceder de las condiciones de la tarifa facilitada.

El parser rechaza lotes vacíos, estructuras incompatibles, importes inválidos,
cantidades no enteras o cero, duplicados e inconsistencias de IVA. Preserva precisión
decimal y no calcula IVA de transporte desconocido. Las importaciones son atómicas,
registran errores, conservan historial y permiten repetir archivos sin duplicarlos.

Solo se exportan precios actuales y su contexto, no todo el catálogo relacional.
No están implementados: recorrido completo del catálogo, importación de etiquetas traducidas,
dependencias generales, baja de productos, FastAPI, panel web, planificador mensual,
checkpoints de catálogo ni WordPress. Las carpetas correspondientes son puntos de
extensión. No se ha validado ninguna tarifa contra una respuesta real completa.

## Próximo paso

Con la autorización declarada, inspeccionar los sitemaps de catálogo anunciados y
una ficha de producto. Identificar sus datos públicos y validar una configuración
con precios antes de ampliar la recogida. USS-Connect o un feed siguen siendo
alternativas para la integración.
