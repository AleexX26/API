# Producto de prueba: Flyers/Folletos doblados (Print24 ES)

27-10-2026. URL: `https://print24.com/es/productos-impresion/flyers` (de `catalog_urls`, tipo `product`).
Una sola petición GET (HTTP 200, 1,4 MB, `text/html`), permitida por robots.txt, sin cookies,
sin login, sin llamar a ninguna API. Sin captcha ni bloqueo. Guardado en `data/product-probe/`:

- `flyers.html`: respuesta original (sha256 `7cd74ae3…c6c7`).
- `flyers.flight.txt`: los datos incrustados, ya descodificados.
- `flyers.calculationData.json`: el bloque del configurador, extraído tal cual.

## Dónde están los datos

La web es Next.js. La página trae los datos del configurador **dentro del propio HTML**, en los
fragmentos `self.__next_f.push([1,"…"])`. Unidos y descodificados contienen
`defaultProductPageData.calculationData` con:

| Clave | Qué contiene |
|---|---|
| `itemMaster.boxes` | 22 grupos de opciones (formato, papel, tintas, acabados, cantidad, envío…) con todos sus valores y los textos en español |
| `itemMaster.selectedProps` | la configuración por defecto |
| `priceMatrix` | precios de **esa configuración por defecto**: 5 cantidades × 3 tipos de envío |
| `productQuantities`, `countries`, `factSheet` | cantidades, países de entrega, ficha técnica |

No hace falta ejecutar JavaScript ni llamar a ninguna API para leer esto.

## Opciones (grupos y número de valores)

Visibles: páginas 8, formato 17 (más formato libre), orientación 2, papel 46, tintas 10,
procesamiento 2, acabado 2, perforación 5, prueba 2, cantidad 70, diseños/modelos 2, motivos 10,
empaquetado 3, envío 3. Ocultos con un solo valor fijo: disponibilidad, calidad (2), núcleo
de papel, accesorios (18, sobres), tamaño de acabado.
Cada valor trae `pgrId` (id estable), `propertyAliasName` y el texto traducido.

Ejemplo de la configuración por defecto (`deepLink`):
`item_group_id=9&delivery_country_code=ES&properties=3765|4560|1015|222|6309|3783|3774|4119|115|1197|1209|14|4016|1147|1138|823|840|6003|400|8673|9454|6400|3764&variants=27&product_alias_id=63`
(DIN A6 vertical, 1 cara, 115 g estucado brillante, 4+0, 100 unidades).

## Precios de la configuración por defecto (neto, EUR, entrega a España, IVA 21 %)

| Unidades | Estándar (5 d) | Exprés (4 d) | Prioridad (1 d) |
|---|---|---|---|
| 100 | 16,05 | 22,97 | 36,21 |
| 125 | 18,15 | 25,59 | 39,14 |
| 150 | 18,40 | 25,90 | 39,49 |
| 175 | 18,65 | 26,21 | 39,84 |
| 200 | 18,90 | 26,52 | 40,19 |

Comprobado: 100 uds estándar = producto 11,13 + envío 4,92 = 16,05 neto; + IVA 3,37 = 19,42 bruto.
Son precios públicos de la web sin sesión: no hay prueba de que coincidan con una tarifa de cuenta.

## Adaptación del parser (hecha)

Tras revisar el parser contra la respuesta real, las diferencias eran solo estas (corrijo mi primer análisis,
que citaba dos que no eran ciertas: `delivery_text_translated` sí existe y el parser ya leía decimales JSON):

1. `shipping_type` está dentro de `quantity` (`row.quantity.shipping_type`); se acepta también la forma antigua.
2. `shipping_net` y `total_vat` solo vienen como texto (`"4,92 €"`): se interpretan con `es_money`, y
   `shipping_net` se comprueba contra `total_net − product_net` (si no cuadra, el lote se rechaza).
3. `quantity.id` (p. ej. `400`) es un id; las unidades están en `price.quantity_value`.

Nuevo `app/parsers/product_page.py`: extrae de un HTML guardado la configuración por defecto y su matriz.
Se excluyen de la identidad de la configuración `quantity` y `shipping_type`, porque la matriz los recorre.
`valid_until` = observación + 31 días: es nuestro plazo de refresco, no una promesa de Print24.
Comando local (sin red): `main.py --db <bd> import-page data/product-probe/flyers.html --url <url>`.

## Lo que NO sé todavía

- **Qué combinaciones de opciones son válidas.** La página lista todos los valores de cada grupo,
  pero no las dependencias entre ellos. Multiplicar opciones daría combinaciones imposibles.
- **Cómo se obtiene el precio de otra configuración.** Aquí solo viene la de por defecto. Lo
  probable es que el configurador llame a `price-matrix` / `productFeature` al cambiar una opción
  (los endpoints que aportaste), pero no los he llamado ni verificado.
- Cuántas configuraciones razonables tiene un producto (se debe decidir qué cobertura se quiere).
- Si el catálogo completo sigue este mismo formato: solo he visto un producto.

## Preguntas para ti

1. ¿Qué cobertura quieres? (a) solo la configuración por defecto de cada producto, que es gratis y ya
   está en la página; (b) un conjunto limitado de configuraciones elegidas por ti; (c) todas.
2. ¿Permito probar **una** llamada al endpoint `price-matrix` con una opción cambiada, para ver si
   funciona sin sesión? Eso sería ya una API, no la web pública, y prefiero tu confirmación.
