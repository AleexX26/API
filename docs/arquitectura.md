# Arquitectura mínima y evolución

Implementado: archivo local → parser Decimal → importación transaccional → SQLite
→ exportación JSON/CSV. CLI con inicialización, importación, estado y exportación.
No hay dependencias de red de producción. `pytest` es una dependencia de desarrollo.

## Identidad y persistencia

La configuración usa SHA-256 del JSON canónico de producto, pares grupo/opción
ordenados, país, moneda, ámbito de cuenta/tarifa y servicios adicionales. Las
cantidades y modalidades de envío son dimensiones independientes del precio.
No se generan combinaciones nuevas. Las opciones importadas solamente describen
selecciones explícitas; no significan que puedan combinarse libremente.

`schema.sql` crea categorías jerárquicas, productos, asociación de categorías,
grupos, opciones, asociación producto/opción, configuraciones y sus opciones,
cantidades por producto, modalidades de envío, precios actuales, historial,
ejecuciones y errores. Los nombres traducidos admiten NULL cuando no se conocen;
no se inventan descripciones. Su importador se incorporará al recibir datos reales.

Importes en TEXT decimal en SQLite para evitar conversiones a float; cálculos
exclusivamente Decimal. Para PostgreSQL: migrar importes a NUMERIC con precisión
acordada, fechas a TIMESTAMPTZ, claves autogeneradas a IDENTITY y usar migraciones
versionadas. El esquema SQLite no se presenta como SQL directamente portable.
La versión 1 se registra; todavía no existe motor de migraciones incrementales.

Cada importación registra procedencia, hash y ejecución. Una transacción engloba
configuración y ofertas: fallo → rollback completo → error en ejecución separada.
Una actualización conserva la fila anterior completa en price_history, incluso
si solo cambia la fecha de observación. Repetir un archivo y contexto idénticos no
duplica precios ni historial. Observaciones antiguas o contradictorias con la misma
fecha se rechazan. Caducidad explícita; no se prolonga automáticamente tras fallos.
El prototipo admite reintentar archivos enteros, no checkpoints parciales ni
recuperación automática de procesos terminados abruptamente.

Transporte bruto queda NULL. Neto unitario = neto producto / unidades, sin transporte
ni redondeo monetario anticipado. Tolerancia técnica de 0,01 para neto + IVA = bruto;
debe ajustarse al contrato de moneda/redondeo real. No se fuerza producto + transporte
= total, porque puede haber servicios adicionales o descuentos aún no documentados.
Los campos de plazo se conservan como texto sin inventar fechas de entrega.

## Fases siguientes (diseño, todavía sin implementar)

1. Un producto real: comprobar evidencia, parser y catálogo de opciones traducidas.
2. Adaptador de feed autorizado: reglas de dependencias y cuarentena de registros
   no interpretables; snapshots completos identificados. Solo marcar descatalogados
   tras recibir y validar un snapshot completo, nunca por ausencia en uno parcial.
3. Sincronización mensual mediante Programador de tareas de Windows o cron; bloqueo
   de ejecución concurrente, staging, checkpoints, publicación atómica y métricas.
   No fijar límites HTTP inventados: acordarlos con el proveedor; acceso secuencial
   y reintentos limitados cuando se implemente el adaptador.
4. FastAPI con acceso exclusivamente local a datos publicados:

| Ruta prevista | Contrato propuesto |
|---|---|
| GET /api/categories | Jerarquía local |
| GET /api/products | Productos activos, paginados |
| GET /api/products/{id} | Producto o 404 |
| GET /api/products/{id}/options | Opciones y selecciones válidas conocidas |
| POST /api/quotes | Identidad exacta, cantidad, envío; sin coincidencia 404, caducado 409 |
| GET /api/sync/status | Última ejecución, errores, vigencia y programación |

Estos endpoints son diseño de nuestra aplicación, no endpoints de Print24.
Importes como strings y moneda explícita; nunca elegir silenciosamente una
configuración aproximada. No servir fixtures de prueba a WooCommerce.

5. Panel local: contadores, última sincronización, errores, productos sin precio,
   variaciones y próxima actualización; botón para iniciar una importación autorizada
   con autenticación administrativa. FastAPI en loopback, sin exposición pública por
   defecto. El panel y el planificador no forman parte de esta primera entrega.
6. Plugin WordPress posterior: cotización local, margen comercial separado del coste,
   selección de variantes válidas e integración WooCommerce. Revalidar vigencia al
   cerrar el pedido. El precio mensual puede quedar obsoleto antes de la siguiente carga.
