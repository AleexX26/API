# Cómo funciona el comparador

Explicación sencilla de qué lenguajes usa, de dónde salen los precios y qué pasa cuando alguien busca algo o pega
«el pedido de un cliente». Para el detalle técnico: `CLAUDE.md` (decisiones) y `docs/arquitectura.md`.

## Resumen en una frase

Unos programas en **Python** visitan las webs de los proveedores y guardan sus precios en una base de datos
**SQLite**; un servidor en Python (**FastAPI**) lee esa base y se la sirve a una página web hecha con **HTML, CSS y
JavaScript** normales. **No hay PHP**: el PHP que aparece en el proyecto es el de las webs de los proveedores (por ejemplo
Printai) y el del plugin de WordPress de `BotWP/`, que es otro proyecto.

## Qué tecnología hay en cada parte

| Parte | Tecnología | Dónde está |
|---|---|---|
| Recogida de precios | Python (`requests`) y, en 3 casos, un navegador automático (Playwright/Chromium) | `app/collectors/` |
| Lectura de las páginas | Python: extrae el JSON del configurador, las opciones y los precios | `app/parsers/` |
| Base de datos | SQLite, un archivo local, sin servidor de base de datos | `data/catalog.sqlite3` y `data/workbench.sqlite3` |
| Lógica (filtros, comparación, IVA) | Python | `app/services/` |
| Servidor web y API | FastAPI + Uvicorn | `app/api/web.py`, `web_server.py` |
| Pantallas | HTML + CSS + JavaScript sin framework | `web/` (`index.html`, `app.js`, `tarjetas.js`, `style.css`) |
| Pruebas | pytest y Playwright (navegador a 375 px y 1440 px, contraste de color) | `tests/` |
| Scripts de uso | `.cmd` de Windows | `Abrir comparador.cmd`, `herramientas/Herramientas.cmd` |

## El recorrido completo

```
Webs de los proveedores
        │  (recogida: robots.txt, 5 s entre peticiones, sin cuentas)
        ▼
 app/collectors  ──►  data/cache (HTML guardado, 30 días)
        │
        ▼
 data/catalog.sqlite3   ◄── Excel de tarifas de nuestra web (herramientas, opción 2)
        │                    precios anotados a mano ► data/workbench.sqlite3
        ▼
 FastAPI (app/api/web.py)  ── lee la base y filtra ──►  JSON
        ▼
 Navegador (web/*.js)  ── dibuja botones, tarjetas por proveedor, diferencias de precio
```

1. **Recoger.** Los recolectores visitan las fichas de cada proveedor y guardan el HTML en `data/cache` para no pedirlo
   otra vez. Cada proveedor es distinto: Print24 trae sus precios dentro de la página; Onlineprinters y Printai tienen
   su propio formato; nuestra web se lee con un navegador automático o desde el Excel.
2. **Guardar.** Todo acaba en SQLite. Print24 en tablas propias (`prices`, `configurations`…); el resto en una tabla común,
   `supplier_offers` (proveedor, producto, cantidad, precio, si lleva IVA, si el envío va incluido, plazo, características).
3. **Servir.** Al abrir `http://127.0.0.1:8765`, el servidor entrega la página y responde a las peticiones de la página.
   Para ir rápido guarda los productos en memoria y solo vuelve a leer la base cuando cambia el archivo.
4. **Mostrar.** El JavaScript de `web/` pide los datos al servidor y dibuja los botones, una tarjeta por proveedor, el precio
   sin IVA grande y con IVA pequeño, y la diferencia con nuestra web.

## Qué pasa cuando se elige algo con los botones

Cada botón (cantidad, tamaño, caras, gramaje, papel, acabado…) manda una petición a `/api/catalog` con esos valores.
El servidor recorre los productos recogidos y se queda con los que cumplen **todo**; si un proveedor no tiene ninguna ficha
exacta, enseña la «más parecida» marcada como tal (por ejemplo 300 g en vez de 350 g). Después calcula el precio a la
cantidad pedida y la web ordena por precio con IVA, dejando nuestra web la última.

## «Tengo el pedido de un cliente»

Tu intuición es correcta: busca en el texto **el producto** y luego **la cantidad y las características**. Detalles:

- **No usa inteligencia artificial ni ningún servicio externo.** Son reglas escritas a mano en Python
  (`app/services/request_parser.py`) y el texto del cliente no sale del ordenador.
- El navegador manda el texto a `POST /api/parse-request`; el servidor lo analiza y devuelve lo que ha entendido.
- **Producto:** busca palabras de una lista (unas 60: «tarjetas de visita», «flyers», «camisetas», «lonas»…, con singular y
  plural y sinónimos). Si no encuentra ninguna, no entiende el pedido.
- **Varios productos en un texto:** lo parte por líneas y por `;`, y también cuando aparece «número + producto» otra vez.
  Sale un botón por producto.
- **Después, sobre ese mismo trozo de texto, busca con expresiones regulares:**
  - tamaño: `85x55`, `85 x 55 mm`, `A5`, `DL`;
  - gramaje: `350 g`, `350 gr`, `350 gramos`;
  - caras: «por las dos caras», «2 caras», `4/4`, «una cara», `4/0`…;
  - plazo: «en 3 días», «máximo 5 días»;
  - acabado: plastificado, barniz, mate, brillo, relieve, kraft…;
  - cantidad: el número pegado a «unidades/uds» o delante del producto («500 tarjetas»); `1.000` se entiende como mil.
- Lo que no entiende **se deja fuera y se enseña**, para que la persona lo corrija. El acabado se muestra pero no se usa
  para descartar fichas (las páginas casi nunca lo nombran).
- El resultado rellena los botones de la pantalla y vuelve a lanzar la búsqueda. Un pedido de tarjetas vuelve a la
  pantalla guiada; uno de otro producto rellena el buscador y enseña el catálogo.

## Dónde se guarda cada cosa

- `data/catalog.sqlite3`: todo lo recogido (se puede regenerar volviendo a recoger).
- `data/workbench.sqlite3`: lo que se escribe a mano: precios anotados y presupuestos. **No se regenera**: si se pierde, se pierde.
- `data/cache/`: HTML descargado de los proveedores.
- Nada de esto va a GitHub; para pasarlo a otro PC se usa `herramientas/Herramientas.cmd` → 6 (empaquetar).

## Límites que conviene recordar

- Un precio solo es tan bueno como la última vez que se recogió; la web avisa de los datos de más de 30 días.
- Printai solo da un precio por ficha (su `robots.txt` prohíbe las rutas que calculan el resto): las demás cantidades se anotan a mano.
- El comparador es local y de consulta: no cambia nada en los proveedores ni en WooCommerce.
