# Herramientas

Lo que se usa a diario está fuera, en la carpeta principal: **`Abrir comparador.cmd`** y
**`Abrir comparador para la oficina.cmd`**. Aquí está todo lo demás, para instalar, recoger datos y pasar el proyecto a otro PC.

| Archivo | Qué hace | Cuándo |
|---|---|---|
| `instalar_todo.bat` | Instala Git y Python, descarga el código de GitHub, descomprime `API-datos.zip` y prepara el entorno | PC nuevo, desde cero. Se puede copiar suelto al PC nuevo |
| `preparar_pc_nuevo.cmd` | Crea el entorno de Python e instala lo necesario, y pasa los tests | Una vez, tras copiar la carpeta (lo llama `instalar_todo.bat`) |
| `empaquetar_para_otro_pc.cmd` | Crea `dist\API-para-otro-pc.zip` con todo lo necesario | Para llevar el proyecto entero a otro PC |
| `recogida\reanudar_recogida.cmd` | Recoge Onlineprinters y Printai en segundo plano | Para ampliar los datos (en UN solo PC a la vez) |
| `recogida\recoger_print24.cmd` | Recoge las fichas de Print24 que faltan | Idem |
| `recogida\estado_recogida.cmd` | Muestra cuántas páginas hay de cada proveedor y qué falta | Para ver cómo va |
| `recogida\parar_recogida.cmd` | Para todas las recogidas sin perder lo guardado | Antes de empaquetar o de cambiar de PC |

Todos los scripts se pueden ejecutar con doble clic desde cualquier sitio: ellos mismos se colocan en la carpeta del proyecto.
