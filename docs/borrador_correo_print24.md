# Borrador de correo a Print24 (no enviado)

Estado: borrador. No se ha enviado nada. Rellena los campos entre corchetes antes de enviarlo.
Destinatario sugerido: atención al cliente o programa de socios de Print24 España (el contacto exacto no lo conozco:
búscalo en https://print24.com/es o en https://unitedprint.com/es/socio-de-tienda/, el programa de socios de tienda
de Unitedprint, empresa propietaria de Print24).

---

**Asunto:** Solicitud de acceso a USS-Connect (API de precios) o a un archivo de tarifas

Buenos días:

Les escribo en nombre de [empresa / nombre comercial], con NIF [NIF] y número de cliente [número de cliente, si lo tienen].
Somos [breve descripción: por ejemplo, una agencia / tienda que trabaja con impresión bajo pedido] y compramos
regularmente en Print24 [indicar si tienen cuenta y desde cuándo].

Queremos disponer de los precios de sus productos de forma estructurada para poder comparar costes entre proveedores
de impresión y, más adelante, ofrecer presupuestos a nuestros clientes a través de nuestra tienda [WooCommerce, si procede].
Por eso les pedimos una de estas dos opciones, la que les resulte más sencilla:

**Opción A. Acceso a USS-Connect (API REST)**
Hemos visto que Print24 ofrece USS-Connect, con operaciones como `showitems` y `getprice`. Les pedimos:
1. La documentación vigente y las condiciones de uso, y las credenciales o el procedimiento para solicitarlas.
2. Un entorno de pruebas, si existe.
3. Los límites de uso (peticiones por minuto o por día) y cómo prefieren que espaciemos las consultas.
4. Cómo consultar el precio de **cualquier configuración válida** de un producto (formato, papel, tintas, acabados,
   cantidad, tipo de envío), y cómo conocer qué combinaciones son válidas.

**Opción B. Archivo de tarifas**
Si prefieren no abrir acceso a la API, un archivo periódico (CSV, JSON o Excel) con, para cada producto:
- identificador de producto y de cada opción, con su nombre en español;
- combinaciones válidas de opciones;
- cantidades disponibles y precio por cantidad;
- precio de producto, de envío por tipo (estándar, exprés, prioridad) y plazos de entrega;
- moneda, y si los importes son netos o con IVA;
- fecha de validez de la tarifa.
Nos bastaría con una actualización mensual.

**Condiciones de uso. Necesitamos su confirmación por escrito sobre:**
- si podemos almacenar estos precios en una base de datos propia y actualizarlos una vez al mes;
- si podemos mostrarlos en una herramienta interna de comparación y, en su caso, en nuestra tienda con nuestro margen;
- si nuestra tarifa de cuenta (descuentos acordados) se refleja en lo que devuelve la API o el archivo, o si se trata
  de precios públicos.

Quedamos a su disposición para una llamada si les resulta más cómodo.

Un cordial saludo,

[Nombre y apellidos]
[Cargo]
[Empresa]
[Teléfono] · [Correo]

---

## Notas para ti (no incluir en el correo)

- **Qué hemos hecho hasta ahora:** el proyecto ha leído páginas públicas de producto de Print24 (sus fichas, con la
  configuración por defecto) respetando su `robots.txt` y con 5 segundos entre peticiones. Si quieres ser transparente,
  puedes añadir una frase diciéndolo. Tampoco hace falta mencionarlo: decídelo tú.
- **No se ha usado** ninguna cuenta ni credencial, y no se han esquivado comprobaciones de la web.
- **Por qué piden esto:** las otras configuraciones (otro papel, formato o acabado) solo se obtienen llamando a su calculador, que
  no responde a programas. La vía oficial es USS-Connect (ver `docs/investigacion_api.md`) o un archivo de tarifas.
- **Credenciales:** si te dan acceso a la API, el proyecto no guarda contraseñas ni tokens en el código; habría que decidir
  cómo cargarlos (variable de entorno local, fuera del repositorio).
- **Datos que conviene que tengas a mano:** NIF, número de cliente y si tu cuenta tiene descuentos acordados.
