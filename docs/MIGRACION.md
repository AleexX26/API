# Pasar el proyecto a otro PC y seguir la recogida allí

Los scripts están en la carpeta `herramientas\` (ver `herramientas\LEEME.md`).
El código viaja por GitHub (`git push` / `git pull`) y los datos por ZIP, porque pesan y cambian mucho.

## PC nuevo, desde cero

1. Copia al PC nuevo solo estos dos archivos (están en `dist\` de este PC):
   - `herramientas\instalar_todo.bat`
   - `API-datos.zip` (la base de datos y las páginas descargadas)
2. Ponlos juntos en una carpeta y haz doble clic en `instalar_todo.bat`.
   Instala Git y Python, descarga el código en `Escritorio\Proyectos\API`, descomprime los datos y prepara el entorno.
   Si el repositorio es privado, se abrirá el navegador para iniciar sesión en GitHub.
3. Abre el comparador con `Abrir comparador.cmd`.

## PC que ya lo tiene

- Código: `git pull` dentro de la carpeta `API`.
- Datos: no hace falta tocarlos. Si quieres los de otro PC, ver «Pasar los datos» más abajo.

## Recoger datos (en UN solo PC a la vez)

| Para | Haz doble clic en |
|---|---|
| Onlineprinters y Printai | `herramientas\recogida\reanudar_recogida.cmd` |
| Fichas de Print24 | `herramientas\recogida\recoger_print24.cmd` |
| Ver cómo va | `herramientas\recogida\estado_recogida.cmd` |
| Pararlo | `herramientas\recogida\parar_recogida.cmd` |

- Las recogidas respetan las reglas del proyecto: `robots.txt`, 5 s entre peticiones, sin cuentas ni cookies (ver `CLAUDE.md`).
- Lo ya descargado sale de `data\cache` y no se vuelve a pedir; solo se piden las páginas que faltan.
- Mientras dure, en Configuración → Sistema → Energía pon «Suspender: nunca». Si el PC se apaga, no se pierde nada: vuelve a lanzarlo.
- TusKamisetas (15.468 productos, unas 21 h) no se incluye por defecto; para añadirlo, quita el `rem` de su línea en `reanudar_recogida.cmd`.

## Pasar los datos entre PC

1. En el PC que recogió: `herramientas\recogida\parar_recogida.cmd` y luego `herramientas\empaquetar_para_otro_pc.cmd`
   (crea `dist\API-para-otro-pc.zip`). Para solo los datos, comprime la carpeta `data` en `API-datos.zip`.
2. Copia el ZIP al otro PC y descomprímelo en la carpeta `API` (los datos van en `API\data`).
3. **Cuidado:** esto sustituye la base de datos del destino. Si los dos PC han recogido cosas distintas, hace falta unirlas
   (script de fusión, pendiente), no copiar una encima de otra.

## Avisos

- No ejecutes la recogida en los dos PC a la vez: duplicarías las peticiones y se mezclarían los datos.
- No se traslada la prueba de variaciones de Print24 (navegador): está sin ejecutar. Las otras configuraciones de Print24
  requieren pedirlas a Print24 (ver `docs/borrador_correo_print24.md`).
- Si al abrir algo ves «did not find executable» o un error de Python, es un `.venv` copiado de otro PC:
  ejecuta de nuevo `herramientas\preparar_pc_nuevo.cmd`.
- Si falta `data\cache`, la recogida funciona igual pero empieza de cero.
