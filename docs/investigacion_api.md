# Investigación de integración Print24

## Actualización: autorización y prueba pública

El 27-10-2026 el usuario confirmó en el chat: «si tengo autorizacion», en el contexto
del scraping de Print24. Se registra como autorización declarada por el usuario;
no se ha revisado un contrato ni se deducen permisos para eludir restricciones.
Esta confirmación sustituye el bloqueo operativo por falta de autorización señalado
en la investigación inicial que se conserva debajo.

Se consultó directamente `https://print24.com/robots.txt` (HTTP 200): publica
`Allow: /es`, `Disallow: /es-`, `Disallow: */freedesign/*` y anuncia
`https://print24.com/es/sitemap_index.xml`. Robots expresa reglas de rastreo, no
una licencia comercial. No se usó su regla de API para inferir autorización de endpoints.

Prueba del colector: tres solicitudes GET secuenciales (robots, índice, portada),
todas HTTP 200, sin credenciales, cookies ni redirecciones. Antes se hizo una consulta
directa adicional de robots para investigar su contenido. El índice contiene 9
sitemaps, entre ellos `sitemap_category.xml`, `sitemap_product.xml` y
`sitemap_productvariant.xml`; la portada contiene 48 enlaces internos únicos del
ámbito español. Estos enlaces incluyen páginas informativas: no son 48 productos.
No se descargaron sitemaps secundarios ni se interpretaron precios.

Evidencias originales y hashes: `data/discovery-20261027-01/manifest.json`,
`robots.txt`, `sitemap.xml`, `homepage.html`. Las rutas anteriores proceden de
esas respuestas reales, no de conjeturas. Próximo paso: inspección acotada de los
sitemaps específicos y una ficha, sin recorrer todas las configuraciones.

## Investigación inicial (anterior a la confirmación del usuario)

Fecha de revisión: 27-10-2026. Alcance: primera tarea, sin consultas a servicios
de cálculo, sin autenticación y sin recopilación automática del catálogo.

## Evidencias públicas

1. [USS-Connect REST API](https://secure.unitedprint.com/download_rest.html).
   El resultado indexado del dominio del proveedor describe una API para cuentas
   Print24 con correo y contraseña, un ejemplo PHP y operaciones como `showitems`
   y `getprice`. Publica las bases `https://print24.com` y
   `https://print24.onts.unitedprint.dev`. La apertura directa devolvió 502 en la
   herramienta de investigación: la evidencia disponible es el contenido indexado,
   no una prueba de funcionamiento. No se descargó ni ejecutó el PHP. No conocemos
   rutas operativas, contratos actuales, formato de login ni límites.
2. [Print24 España](https://print24.com/es) enlaza una oferta de tienda asociada a
   [Unitedprint Shop Services](https://unitedprint.com/es/socio-de-tienda/).
   Es una alternativa comercial que merece consultar. La existencia de ese programa
   no demuestra acceso a un feed para una tienda WooCommerce independiente.
3. [Condiciones generales](https://print24.com/es/condiciones-generales), leídas
   como fuente pública de contratación. Regulan pedidos y registro (art. 3), precios
   y transporte (art. 13), y plazos indicativos (art. 15). No se ha identificado una
   licencia específica de extracción masiva, almacenamiento mensual o republicación
   de tarifas. No inferimos autorización de la mera accesibilidad de la web.

Conclusión operativa: existe una pista oficial de integración, pero no acceso
autorizado confirmado para este proyecto. No se implementa un cliente HTTP ni se
prueban los endpoints internos. Solicitar condiciones vigentes de USS-Connect o un
feed de tarifas autorizado. No confundir Print24 con Print.com, Print.one u otros.

## Endpoints aportados por el usuario

Son observaciones preliminares del usuario, **no verificados contra el servidor en
esta ejecución**. Ningún endpoint de cálculo tiene validación independiente todavía.

| Método / ruta | Evidencia y función | Pendiente |
|---|---|---|
| POST `https://print24.com/api/es/itemmaster/calculation/price-matrix` | Payload completo aportado; campos de salida enumerados; precios por cantidad y envío | Respuesta completa, errores, tipos, moneda, permisos, límites y autenticación |
| POST `https://print24.com/api/es/itemmaster/calculation/productFeature/` | Fragmento `prop_details` y nombres de producto aportados; interpreta una selección | Payload, contrato y cobertura; no demuestra enumeración de opciones |
| `/api/es/calculation/file-check/select-boxes` | Opciones de comprobación de archivo según observación aportada | Método y contrato; no es catálogo |
| `/api/es/shopping-cart/product-data` | Resultado `0` observado | Método, contexto y utilidad; no inferir estructura |
| `productDetails/` | Nombre parcial | URL completa, método y todos los parámetros |

Payload conocido de price-matrix: `delivery_country_code` (`ES`),
`product_alias_id` (`2`), `properties` (pares `id`, `name`), `quantities`
(identificadores, no unidades físicas), `premium_file_check` (`0`). Ningún campo
puede declararse opcional ni interpretarse como enumeración exhaustiva. Los 13 pares
aportados describen una selección; el fragmento de carteles A3 de productFeature no
se ha vinculado técnicamente con esa selección. No mezclarlos como una sola captura.

Respuesta descrita: array con `quantity.id`, `shipping_type[]`, `delivery_days`,
`delivery_type`, `delivery_text_translated`, `price.quantity_value` y
`price.final_prices.{product_net_value,total_net_value,total_gross_value,shipping_net,total_vat}`.
El parser implementa esas rutas de forma provisional. Los importes de tests son
sintéticos: no son respuestas anonimizadas ni cotizaciones reales. No había archivos
JSON en la carpeta inicial. Se conservan ambos ejemplos originales en
`tests/fixtures/user_examples.json`, sin convertirlos en respuestas verificadas.

## Información necesaria para el catálogo

- Contrato de uso y permiso expreso para caché, reventa, duración e historial.
- API/feed vigente, alta de cuenta, autenticación oficial y entorno de pruebas.
- Listado paginado de productos, categorías, subcategorías e identificadores estables.
- Grupos y valores traducidos, valores por defecto, dependencias y cambios al seleccionar.
- Evidencia de validez de cada configuración. No usar producto cartesiano de opciones.
- Cantidades físicas asociadas a IDs; moneda, fiscalidad, servicios y descuentos por cuenta.
- Desglose IVA del transporte: el IVA total no permite obtenerlo por sí solo.
- Semántica de días laborables, fecha de cálculo, caducidad y disponibilidad.
- Límites, reintentos, 429/Retry-After, versionado y eliminación de productos.

## Alternativa y siguiente validación

Trabajar con una exportación facilitada por Print24 y autorizada para su reutilización.
Mantener el archivo original, su procedencia y hash; adaptar su formato real cuando
exista. El contexto JSON local es un formato nuestro, no un supuesto feed de Print24.
Un nombre de archivo o `validity_evidence` no otorga autorización ni prueba validez.

Pedir una muestra completa de un producto con solicitud/respuesta emparejadas,
opciones y condiciones de precio. Eliminar cookies, tokens, datos personales y
credenciales. Validar manualmente esa muestra antes de ampliar a una categoría.
No se enviaron mensajes al proveedor ni se programó ninguna descarga mensual.
