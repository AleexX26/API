# Validación del prototipo

## Ampliación de descubrimiento web, 27-10-2026

`python -m pytest -q --basetemp .test-runs/discovery1`: **24 passed in 3.36s**.
Incluye alcance de URLs, deduplicación, reglas robots por coincidencia más larga
y comodines, detención ante directivas que requieren revisión y lectura de sitemap XML.
Además se ejecutó el colector real: 3 respuestas HTTP 200, 9 enlaces de sitemaps,
48 enlaces de portada. Evidencias en `data/discovery-20261027-01/`.
Estas pruebas no validan todavía extracción de opciones ni precios reales.

## Validación inicial

27-10-2026. Windows, Python 3.14.8, pytest 9.1.1.

Comando ejecutado desde la raíz:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .test-runs/run3
```

Resultado: **21 passed in 2.78s**. Usar un subdirectorio nuevo para cada ejecución
con `--basetemp`: pytest puede limpiar ese directorio. `.test-runs` se creó dentro
del proyecto porque la carpeta temporal predeterminada del entorno restringido no
permitía crear las carpetas de pytest. Los intentos iniciales produjeron 17 pruebas
correctas y 2 errores de preparación del entorno; se resolvió sin cambiar las aserciones.

Cobertura comprobada:

- Decimal desde strings y números JSON; ausencia explícita de transporte bruto.
- Distinción entre ID de cantidad y unidades; precio neto unitario.
- Rechazo de importes no finitos, float, negativos, booleanos y formatos incompatibles.
- Respuestas vacías/malformadas, duplicados, IVA inconsistente y cantidad cero.
- Identidad canónica independiente del orden de propiedades y sensible a servicios.
- Importación, opciones vinculadas, repetición sin duplicados y actualización mensual
  simulada con conservación del snapshot anterior.
- Fallo de parsing, observación obsoleta y rollback tras una primera escritura del lote.
- Integridad referencial SQLite.
- CLI completa: inicialización, importación, estado y exportaciones JSON/CSV.

Se creó `data/demo.sqlite3` con un producto sintético, una configuración y un precio.
No es una base de producción. No se han probado consultas externas, equivalencia
con una tarifa real, catálogo completo, FastAPI, panel ni programación mensual.

No había fixtures reales disponibles. Los fixtures sintéticos no acreditan que la
forma completa del JSON del proveedor coincida con las rutas descritas: esa prueba
de contrato requiere una captura autorizada completa.
