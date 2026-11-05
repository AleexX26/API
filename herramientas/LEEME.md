# Herramientas

Lo que se usa a diario está fuera, en la carpeta principal: **`Abrir comparador.cmd`** y
**`Abrir comparador para la oficina.cmd`**. Aquí hay solo dos archivos:

| Archivo | Qué hace | Cuándo |
|---|---|---|
| `Herramientas.cmd` | Menú con todo lo demás (ver abajo). También acepta argumento: `Herramientas.cmd recoger`, `importar`, `estado`, `parar`, `preparar`, `empaquetar` | Doble clic |
| `instalar_todo.bat` | Instala Git y Python, descarga el código de GitHub, descomprime `API-datos.zip` y prepara el entorno | PC nuevo, desde cero. Se puede copiar suelto al PC nuevo |

Opciones del menú de `Herramientas.cmd`:

1. **Recoger datos (todo en uno)**: fichas y características de Print24, más cantidades de Print24 hasta 1000, precios de nuestra web (tarjetas, flyers, folletos, trípticos, dípticos y otros 16 productos: unas 600 combinaciones) y, si dices que sí, Onlineprinters y Printai en segundo plano (≈3 h). Lo ya descargado no se vuelve a pedir. En UN solo PC a la vez.
2. **Importar el Excel de tarifas** de nuestra web (arrastra el `.xlsx` o escribe la ruta). Cuando cambie la tarifa.
3. **Ver cómo va** la recogida.
4. **Parar la recogida** sin perder lo guardado (antes de empaquetar o cambiar de PC).
5. **Preparar este PC**: crea el entorno de Python, instala lo necesario y pasa los tests. Una vez.
6. **Empaquetar** `dist\API-para-otro-pc.zip` para llevar el proyecto a otro PC.

Se ejecuta con doble clic desde cualquier sitio: se coloca solo en la carpeta del proyecto.

**Pausa entre pasos.** Al empezar la recogida pregunta la pausa: **humana** (al azar entre 30 s y 1 min, distinta cada vez; recomendada, pero la recogida completa tarda muchas horas: déjala en el otro PC) o **rápida** (5–8 s, solo para pruebas). Se puede cambiar con `--pausa-min` y `--pausa-max` en cada recolector, o con las variables `PAUSA_MIN` y `PAUSA_MAX`; nunca baja de 5 s.
