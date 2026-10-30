# Cómo salen los precios en cada proveedor (prueba de 1 página, 27-10-2026)

Autorización: el usuario confirmó en el chat (27-10-2026) que tiene autorización para los seis proveedores.
Es una declaración suya, no un contrato revisado. Siguen las mismas reglas: robots.txt, 5 s entre peticiones,
sin redirecciones, sin cookies ni login, y parada ante un bloqueo. Una petición GET por proveedor, guardada
en `data/pruebas/provider-probe/` (HTML original, sin versionar). No se llamó a ningún endpoint de cálculo.

| Proveedor | Página probada | ¿Precio público leído? | Qué hay | Límite |
|---|---|---|---|---|
| Print24 | flyers (hecho antes) | Sí | JSON embebido: opciones + matriz de precios de la configuración por defecto | Solo por defecto (ya recogido) |
| Printai | `/flyers/` | **Sí, 1 configuración** | Total de la selección por defecto (DIN A6, 500 uds): 31,24 € + 6,56 IVA = 37,80 €; `ld+json` Offer con 37,80; selects de tamaño (4) y cantidad (6) | El precio de otras opciones lo calcula `/price_calculate.php`, **prohibido por su robots.txt** |
| Onlineprinters | `/k/flyers` | **No** | Página de categoría: tabla de formatos (A8…A4, DL), sin importes | Los precios vienen de otras páginas/producto; su JSON de configuración (`tpl_productConfigurationJson`) está **prohibido por robots.txt** |
| TusKamisetas | `/es/producto/b-c-e150-t-shirt` | **Sí, tabla por tramos** | `ld+json` AggregateOffer (1,41–3,15 €) y tabla precio unitario por cantidad (1, 10, 50, 100, 200, 300, 500, 1000) para Blanco y Color | Precio unitario sin personalización ni envío; impresión se calcula por `/es/ajax/producto/update-price` (no probado) |
| Stricker | `/es/catalogo/` | **No** | Listado de productos (15 por página, scroll por `ajax/aplicaScroll.php`), sin ningún importe | Catálogo B2B: precios tras acceso de cliente («zona reservada»). Sin login no hay precios |
| Truyol | `/es/material-publicitario/flyers` | No comprobado | La descarga **falla por TLS** (cadena con certificado autofirmado) | No desactivo la verificación del certificado. Probar desde otra red o confirmar con ellos |

Nota sobre captcha: la página de Printai contiene reCAPTCHA v3 en sus formularios (boletín/contacto). La página
cargó completa (HTTP 200); no es un bloqueo de acceso. Mi primer detector marcó «captcha» por ese texto y paré
para revisarlo; lo afiné para detectar solo retos reales (`cf-chl-`, «just a moment», «verify you are human»…).

## Qué significa para el comparador

- **Print24** (hecho) y **TusKamisetas** (tabla en HTML) y **Printai** (default en HTML) se pueden automatizar
  con las mismas reglas que Print24, pero solo para la configuración por defecto de cada ficha.
- **Onlineprinters y Printai** esconden el cálculo de otras configuraciones en rutas que su robots.txt prohíbe:
  no se usan. Para Onlineprinters falta encontrar una ficha de producto con precio en el HTML.
- **Stricker**: sin cuenta de revendedor no hay precios. Requiere credenciales; yo no las guardo ni las uso.
- **Truyol**: pendiente de resolver el TLS.
- La parte difícil sigue siendo la equivalencia: el default de cada web son especificaciones distintas
  (tamaño, papel, cantidad), así que cada precio se compara solo tras confirmarlo en la web («Usar como presupuesto»).
