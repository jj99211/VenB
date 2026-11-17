# Cambios

Novedades de cada versión de VenB y VenB Rutas (las dos ediciones comparten número de versión).

## 3.47

- **Planificador, etapas:** con una llegada prevista, la velocidad media en movimiento se calcula para llegar a esa hora y no se puede editar. Ahora la página lo explica junto a «Llegada prevista» y junto al campo de velocidad, que se ve atenuado, y el botón **Quitar la llegada prevista y escribir la velocidad** lo deja editable de nuevo.
- Corregido: en el calendario de fecha y hora, las flechas de mes cerraban el calendario sin dejar elegir el día.

## 3.46

- **Planificador:** en una ruta sin hoja, el último punto se llama por defecto «Llegada» en lugar de «Meta» (también en el GPX con waypoints). Se puede cambiar en la tabla de Previsión.
- Tipos de punto nuevos **🏘️ Población** y **🏞️ Panorámica** (también en las infografías y la página interactiva), además de ⭐ Punto de interés.
- **Perfil más fiel:** el modelo del terreno a veces dibuja dientes de sierra en un puerto continuo (puentes sobre barrancos, desmontes, laderas junto a la carretera), y se notaban en el perfil, en la infografía, en los tiempos y en el GPX descargable. Ahora se quitan las contrapendientes pequeñas y, si el modelo sale claramente dentado y el GPX trae un perfil limpio con un desnivel parecido, se usan las altitudes del GPX. El registro del análisis indica de dónde salen.

## 3.45

- **Infografías:** la leyenda de los tipos de punto y la de la pendiente del track ya no se pueden solapar. Cada una comparte línea solo si cabe entera; si no, baja a una fila propia (y la de tipos se parte en varias si hiciera falta) y el pie crece.
- Incluye todas las novedades de las versiones anteriores, también las de la [3.43](https://github.com/jj99211/VenB/releases/tag/v3.43) (Super Brevet, tiempo límite personal, etapas, puntos en el mapa, nombres de Garmin Connect) y la [3.44](https://github.com/jj99211/VenB/releases/tag/v3.44) (reloj al generar, tiempo en horas y minutos, descanso por noche, tipo Puerto): basta con instalar esta.

## 3.44

- **Planificador, generar:** mientras se generan los documentos, un reloj muestra el tiempo transcurrido y el paso en curso; el registro completo queda plegado en «Ver el detalle del proceso».
- **Tiempo límite o deseado** en horas y minutos: listas desplegables en las que también se puede escribir.
- **Etapas:** cada noche puede tener su propio descanso; el descanso diario es el de partida.
- Tipo de punto nuevo **⛰️ Puerto**, también en las infografías y la página interactiva.
- La explicación de la tabla de Previsión va, más breve, junto a los botones «Añadir punto» y «Actualizar».
- Corregido: en un recorrido libre ya no aparece el campo «Distancia» vacío.

## 3.43

- **Planificador, tipo de ruta y distancia:** la distancia se elige según el tipo: en un brevet, solo las estándar (200 a 1.000 km); en una Super Randonnée, 600 km; en el tipo nuevo **Super Brevet**, de 1.200 a 2.000 km, con los tiempos del reglamento de Randonneurs Mondiaux. En un recorrido libre no se elige distancia.
- **Tiempo límite editable:** se rellena con el oficial, pero se puede cambiar (por ejemplo, una SR cicloturista). Entonces los cálculos son personales y no siguen la tabla oficial, y la página lo explica. Con un tiempo personal o en un recorrido libre, aviso si la media neta queda por debajo de 12 km/h o por encima de 28 km/h.
- **Etapas:** en los brevets de 400 km o más, las SR, los Super Brevets y los recorridos libres, la ruta se puede organizar en varios días (hasta 7): paradas para dormir, descanso diario y llegada prevista, de la que sale la velocidad necesaria.
- **Puntos en el mapa:** con 📍 se elige el punto exacto en un mapa, sobre el track, y VenB propone el nombre de la localidad.
- **Garmin Connect:** los nombres cambiados en Connect llegan a VenB tras cada descarga.

## 3.42

- **Temporadas:** todas las cuentas anuales (km, horas, salidas y desnivel por año, acumulados y mapa por mes del Histórico, kilómetros de brevet y bicis) van por la temporada de Ajustes, que lleva el año en que se disputa: con inicio en noviembre, la temporada 2027 empezó el 01/11/2026. Al cambiar el mes se recalcula todo el historial.
- El inicio de temporada se elige entre septiembre y abril (por defecto, noviembre); el mapa por mes empieza por ese mes y el filtro «Temporada» de Brevets lo sigue. Corregida la temporada de las bicis con inicio en primavera.

## 3.41

- **Brevets:** el historial va en una caja con scroll (unas 15 filas a la vista) con la cabecera fija; los botones **Editar** y **Borrar** son más grandes y claros.
- Las pruebas registradas por etapas («PBP2019_Etapa01», «…_SinGPS» para los km no grabados) cuentan como una sola prueba en el resumen, en los kilómetros por tramo y en el R5000/R10000; los km siguen siendo los reales, sin duplicar.
- **Registrar un brevet** empieza plegado y avisa de que lo registrado a mano no se enlaza con Garmin: las pruebas grabadas (también las SB) se promueven desde el Histórico, una vez por etapa, para no duplicar km.
- El filtro «Actividad» ya no cuenta como enlazadas las filas de km sin grabar.
- **Mejor tiempo por tipo de prueba:** una fila por cada distancia de BRM, las SR, cada superbrevet (PBP, LEL, MGM…) y las Flechas. Las pruebas por etapas compiten con su tiempo total, de la primera salida a la última llegada; las incompletas o con km sin grabar cuentan, pero no compiten.
- Guías rápidas de instalación de una página.

## 3.40

- **Actualización con un clic.** Las versiones se publican en GitHub. VenB avisa en Inicio (VenB Rutas, en el Planificador) y, con **Actualizar ahora**, descarga la versión nueva, comprueba el fichero, se cierra, se instala junto a tus datos y se vuelve a abrir. En **Ayuda > Acerca de** se ve la última comprobación y se puede buscar en el momento. Desde la 3.39 o anteriores hay que instalar esta versión a mano una vez.
- **VenB Rutas usa su propio puerto (8878)**: puede estar abierta a la vez que VenB (8877).
- **Planificador:** el GPX con waypoints está siempre entre los ficheros, también antes de generar, y se rehace al cambiar los puntos. Los ficheros generados se ordenan con las infografías y los mapas arriba y la ruta GPX, la tabla de tiempos y la página interactiva debajo.
- **Brevets:** el historial cabe a lo ancho, una prueba por línea y con la cabecera fija, y se puede filtrar por nombre, año, temporada, tipo, distancia, club, inscripción, homologación, R5000, R10000, actividad enlazada, tiempo frente al límite, fechas y pruebas válidas para la PBP 2027, con el recuento y los km de lo que queda a la vista.
- Guías de instalación y actualización en PDF para cada edición.
- La edición de Randonneurs Andalucía deja de publicarse: VenB Rutas, con el perfil del club, la sustituye y usa los mismos datos.
