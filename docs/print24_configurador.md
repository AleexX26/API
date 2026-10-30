# Cómo calcula precios el configurador de Print24 (observado el 27-10-2026)

Observación en el navegador integrado (sin cuentas ni cookies del usuario; cookies no esenciales rechazadas) de
`https://print24.com/es/productos-impresion/flyers`. Se cambió el formato en el desplegable y se anotó la dirección,
el método y el cuerpo de cada llamada (de las cabeceras solo los nombres; no se guardó ningún valor ni token).

## Llamadas que hace al cambiar una opción (todas POST, JSON, `https://print24.com/api/es/...`)

| Ruta | Para qué |
|---|---|
| `itemmaster/calculation/price-matrix` | **Precios**: devuelve la matriz cantidad × envío de la selección |
| `itemmaster/calculation/productDetails/` | Detalle y texto de la selección |
| `itemmaster/calculation/repo` | Normaliza/valida la selección |
| `itemmaster/calculation/premium-filecheck-price` | Precio de la comprobación premium de archivos |
| `factsheet`, `tooltips`, `itemmaster/product_data/{bleed,margin,distance-size}` | Ficha técnica y medidas |

Al cargar la página además: `itemmaster/calculation/productFeature/` (5 veces), `token/create/expiry` (GET, varias veces),
`auth-check`, `countries`, `shopping-cart/*`.

## Forma exacta de la petición de precios

```json
POST /api/es/itemmaster/calculation/price-matrix
{"delivery_country_code":"ES","product_alias_id":63,
 "properties":[{"id":"3765","name":"availability"}, ... ],   // todos los grupos de la selección, SIN quantity ni shipping_type
 "quantities":["400","378","342","4283","385"],              // ids de las opciones de cantidad (100–200 uds.)
 "premium_file_check":0}
```

Al pasar el formato de DIN A6 a DIN A7 solo cambió `{"id":"222","name":"format"}` → `{"id":"207","name":"format"}`;
el resto de `properties` quedó igual y `quantities` también. La respuesta tiene el mismo formato que ya lee
`app/parsers/price_matrix.py` (envío dentro de `quantity.shipping_type`).

## Qué NO sé todavía

- **Por qué mi llamada de prueba desde Python devolvió 200 con cuerpo vacío.** Mi petición tenía la misma forma, pero:
  (a) cambié el papel a `4109` sin tocar `paper_desc` (pudo ser una combinación inválida), o
  (b) falta un dato de sesión: la página pide antes un token anónimo (`token/create/expiry`) y comprueba `auth-check`.
  No he comprobado cuál de las dos. Para distinguirlo habría que repetir con la selección por defecto exacta.
- **Cabeceras reales:** el registro solo captó una cabecera (`Accept`) de una llamada a un tercero; no pude ver las de `price-matrix`.
- **Cómo cambia el papel** (qué otras propiedades se actualizan a la vez): el desplegable de papel no se abrió de forma fiable en el panel.
- **Reglas de combinación válida** entre opciones: probablemente las resuelve `productFeature/`.

## Consideraciones

- El token anónimo lo entrega la propia web a cualquier visitante. Usarlo en memoria no es guardar credenciales, pero la regla del
  proyecto es no pedir ni guardar contraseñas, cookies ni tokens: conviene que el usuario decida si se permite.
- `robots.txt` de Print24 permite `*/api/*`.

## Resultado de las pruebas desde un programa (27-10-2026, autorizadas por el usuario)

- `GET /api/es/token/create/expiry` desde Python: HTTP 200, cuerpo vacío, sin cookies ni token.
- `POST price-matrix` con la selección por defecto EXACTA de flyers (misma que hace la página): HTTP 200, cuerpo vacío.
- Primera prueba (papel cambiado a 4109): también vacío.

Conclusión: el fallo NO era la combinación de opciones ni la falta de un token que yo pudiera pedir. La web responde con
cuerpo vacío a un cliente que no es un navegador (sesión previa, cabeceras o detección de clientes automáticos).
Imitar un navegador para sortearlo sería evadir esa detección, así que no se hace. Vías legítimas: el acceso oficial
(USS-Connect, operación `getprice`, ver `docs/investigacion_api.md`) o un archivo de tarifas pedido a Print24.
Peticiones guardadas en `data/pruebas/api-probe/` (sin tokens ni cookies).
