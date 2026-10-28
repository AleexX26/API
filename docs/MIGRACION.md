# Pasar el proyecto a otro PC y seguir la recogida allí

Estado al preparar este documento (27-10-2026): las recogidas están **paradas** y la base de datos
(`data/catalog.sqlite3`, 7,7 MB) está en un solo archivo, íntegra y sin nada pendiente.

| Proveedor | Bien | Fallidas | Pendientes | Total |
|---|---|---|---|---|
| TusKamisetas | 146 | 19 | 15.304 | 15.468 |
| Onlineprinters | 239 | 186 | 1.482 | 1.907 |
| Printai | 35 | 95 | 101 | 231 |
| Print24 | 171 | 0 | 0 | 171 |

«Fallidas» son páginas retiradas, sin tabla de precios o cuyos números no cuadran. Es normal que haya muchas.

## 1. En ESTE PC antes de copiar

1. Comprueba que no hay nada en marcha: ejecuta `estado_recogida.cmd` (debe decir «ninguno: esta parado»).
   Si hay algo, ejecuta `parar_recogida.cmd` (también deja la base de datos en un solo archivo).
2. Cierra la web si la tenías abierta.
3. **Opcional, para que la copia sea más ligera:** puedes borrar estas carpetas antes de copiar, porque se recrean
   solas y no hacen falta en el otro PC (ahorras unos 330 MB):
   - `.venv` (22 MB, **no funciona en otro PC**, se recrea en el paso 3)
   - `.venv-browser` (235 MB, solo era para la prueba de variaciones de Print24, que está parada)
   - `.uv-cache` (24 MB) y `.test-runs` (46 MB)
4. Copia la carpeta `API` entera (USB, nube, red…). Lo imprescindible dentro de ella es:
   - `app/`, `web/`, `tests/`, `docs/`, `config/` y los archivos `.cmd`, `.py`, `.toml`, `.txt`, `.md` de la raíz;
   - **`data/`** completa: contiene la base de datos y **`data/cache/` (394 MB)**, que son las páginas ya descargadas.
     Sin esa caché, el otro PC volvería a descargar todo desde cero (TusKamisetas son unas 21 horas).
   - Alternativa: `empaquetar_para_otro_pc.cmd` crea `dist\API-para-otro-pc.zip` con todo lo necesario ya filtrado.

## 2. En el OTRO PC: instalar Python (una vez)

Hace falta **Python 3.11 o superior**. Instálalo desde https://www.python.org/downloads/ marcando
«Add python.exe to PATH», o en una terminal:

```powershell
winget install Python.Python.3.12
```

Cierra y vuelve a abrir la terminal después de instalarlo.

## 3. En el otro PC: preparar el entorno (una vez)

Haz doble clic en **`preparar_pc_nuevo.cmd`**. Hace esto: comprueba Python, borra el `.venv` copiado (no sirve),
crea uno nuevo, instala las dependencias, pasa los tests (deben salir **80 pasados**) y muestra el estado de lo recogido.

## 4. En el otro PC: reanudar la recogida

Haz doble clic en **`reanudar_recogida.cmd`**. Lanza las tres recogidas en segundo plano (ventanas minimizadas: no las cierres).

- Lo ya descargado sale de `data/cache` sin volver a pedirlo; solo se piden las páginas que faltan, con 5 s de pausa.
- Las páginas **fallidas** de Onlineprinters y Printai no se guardan en caché, así que se volverán a pedir una vez
  (unos 15 minutos más). No es un fallo.
- Para ver cómo va: **`estado_recogida.cmd`**. Para pararlo: **`parar_recogida.cmd`**.
- Los registros quedan en `data\registros\`.
- Mientras dure (TusKamisetas ~21 h), en Configuración → Sistema → Energía pon «Suspender: nunca». Si el PC se
  apaga, no se pierde nada: vuelve a ejecutar `reanudar_recogida.cmd`.

## 5. Ver los resultados en el otro PC

Doble clic en **`Abrir comparador.cmd`**: abre la web en http://127.0.0.1:8765 con «Catálogo completo» y la búsqueda.

## Avisos importantes

- **No ejecutes la recogida en los dos PC a la vez.** Duplicarías las peticiones a las webs y se mezclarían los datos.
  Mientras corra en el otro, deja este parado.
- **Para traer los datos de vuelta a este PC** (o al revés): para la recogida, ejecuta `parar_recogida.cmd` y copia
  `data\catalog.sqlite3` (y `data\cache\` si quieres conservar las páginas).
- Las reglas de recogida siguen siendo las mismas en el otro PC (`robots.txt`, 5 s entre peticiones, sin cuentas ni
  cookies; ver `CLAUDE.md`).
- **No** se traslada la prueba de variaciones de Print24 (navegador): está sin ejecutar y bloqueada. Las otras
  configuraciones de Print24 requieren pedirlas a Print24 (ver `docs/borrador_correo_print24.md`).
- Si al abrir algo ves «did not find executable» o un error de Python, es el `.venv` viejo: ejecuta de nuevo `preparar_pc_nuevo.cmd`.
- Si en algún momento el PC nuevo no tiene la copia de `data\cache`, la recogida funciona igual pero empieza de cero.
