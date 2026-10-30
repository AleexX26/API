# Datos (no van a Git)

Todo lo de esta carpeta se genera con las recogidas y se pasa entre PC con `API-datos.zip`
(ver `docs/MIGRACION.md`). Las tarifas y páginas descargadas pueden ser información comercial:
no subir nada de aquí a un repositorio público.

| Qué | Para qué |
|---|---|
| `catalog.sqlite3` | La base de datos del comparador: precios y características de todos los proveedores |
| `catalog_links.json` | Índice de enlaces públicos de cada proveedor (páginas generales de cada producto) |
| `workbench.sqlite3` | Presupuestos manuales guardados desde la web |
| `cache/` | Páginas descargadas tal cual (para no volver a pedirlas en 30 días) |
| `registros/` | Registros de cada recogida (`*.log`, `*.json`); `anteriores/` guarda los de las primeras pruebas |
| `homepage-index/`, `discovery-20261027-01/` | Evidencias de las primeras pruebas; el código lee de aquí los `robots.txt`: no moverlas |
| `pruebas/` | Material de prueba (demo sintética, sondeos de proveedores y exportaciones de ejemplo) |
