# Comparador interno de imprentas

Actualizado: 27-10-2026. Objetivo confirmado por el usuario: centralizar varios
proveedores y comparar dónde resulta más económico producir cada trabajo.
WooCommerce queda como integración posterior; el comparador interno es prioritario.

## Proveedores indicados y evidencia pública

| Proveedor | URL indicada | Resultado de la revisión inicial |
|---|---|---|
| Print24 | https://print24.com/es | Descubrimiento limitado probado; ver investigación y manifiesto local |
| Truyol | https://truyol.com/ | Catálogo público de impresión; no se verificó API ni feed en esta revisión |
| Printai | https://www.printai.es/ | Catálogo y programa de revendedores públicos; API no verificada |
| Onlineprinters | https://www.onlineprinters.es/ | Programa oficial anuncia API op.connect; no se han probado endpoints ni autenticación |
| Stricker | https://www.stricker-europe.com/es/ | Catálogo B2B para revendedores; enlace a servicios digitales redirigió a portada; feed/API no verificados |
| TusKamisetas | https://www.tuskamisetas.com | URL corregida explícitamente por el usuario. Catálogo y calculador públicos; no se confirma API |

Fuentes consultadas:

- [Truyol](https://truyol.com/): navegación de productos de impresión y acabados.
- [Printai revendedores](https://www.printai.es/revendedores.html): condiciones
  comerciales y descuentos sujetos a condiciones; no demuestra acceso técnico.
- [Onlineprinters revendedores](https://www.onlineprinters.es/c/lp/revendedores):
  anuncia op.connect para integrar catálogo, pedidos, archivos y estados de envío.
  Pendientes contrato de tarifas, acceso, permisos de almacenamiento y documentación.
- [Stricker](https://www.stricker-europe.com/es/): venta B2B a revendedores y enlace
  de servicios digitales; no basta para afirmar disponibilidad de una API.
- [TusKamisetas](https://www.tuskamisetas.com/es) y
  [condiciones](https://www.tuskamisetas.com/es/terminos-de-uso): calculador por
  cantidades, tallas, colores y personalización. El presupuesto se confirma después;
  distinguir estimación online y oferta firme. La apertura de `/api` no fue accesible
  mediante la herramienta web; esto no demuestra ni existencia ni inexistencia.
  El usuario ha corregido el enlace a la raíz, sin afirmar que exista API.

Solo se revisó información pública; no se iniciaron sesiones ni se extrajeron tarifas
en lote de los cinco nuevos proveedores. La autorización declarada anteriormente
se refería a Print24; no se amplía automáticamente a otros dominios.

## Requisitos de comparación

Cada oferta debe conservar proveedor, referencia original, cuenta/tarifa, moneda,
destino, fecha de observación, caducidad, cantidades y especificación completa.
Comparar coste neto total incluido transporte y servicios obligatorios, mostrando
también IVA y bruto. No descontar dos veces ni aplicar descuentos máximos publicitados
como si fueran los descuentos efectivos de la cuenta.

Equivalencias según familia:

- Papel: medidas, gramaje, soporte, caras, tintas, plegado y acabados.
- Textil: marca/modelo o equivalencia aprobada, composición, gramaje, tallas, colores,
  técnica de impresión, ubicaciones, área y costes de preparación.
- Promocional: artículo/modelo, material, dimensiones, stock y marcaje.

Solo ordenar ofertas equivalentes, vigentes, con costes completos y plazo compatible.
Ofertas incompletas o aproximadas se muestran aparte, sin declararlas las más baratas.
No basta comparar nombres ni precios «desde». Stock y plazos pueden cambiar antes
de una actualización mensual; su frescura debe mostrarse por separado.

## Cambio de arquitectura previsto

El esquema actual es monoproveedor Print24. No cargar otros proveedores en sus tablas
sin migración: los identificadores podrían colisionar. Próxima evolución:
`suppliers`, IDs originales únicos por proveedor, adaptador por fuente y una capa
de especificaciones normalizadas con equivalencias revisadas. Incluir proveedor en
identidades canónicas e historial, conservando los datos actuales con una migración
versionada y copia previa. Esta revisión documenta el diseño; no modifica SQLite.

Primer hito: comparar un trabajo real equivalente entre dos proveedores, con precio
público o tarifa de cuenta identificada explícitamente. Después ampliar familias y
proveedores. Pendiente saber si el usuario tiene tarifas profesionales negociadas.
