# Cambios

Novedades de cada versión de VenB y VenB Rutas (las dos ediciones comparten número de versión).

## 3.56

- **Inicio, nuevo orden:** **Últimas actividades** sube una fila, justo después de «Forma y fatiga». En la última fila, la tarjeta de la izquierda reúne **Últimos informes semanales** (enlace al PDF del último informe y **Seguir leyendo informes**) y **Últimas notas** (la nota más reciente, recortada, con **Seguir leyendo…** y el formulario desplegable **Escribir una nota**). A la derecha siguen Próximos eventos y Anotar peso.

## 3.55

- **Informe semanal automático:** cada lunes, al abrir VenB, se prepara el informe de la semana anterior (de lunes a domingo) en un PDF de una página: horas, km y salidas de bici frente a la semana anterior y a la media de cuatro semanas; forma, fatiga y frescura (CTL, ATL y TSB); TSS; sueño, FC en reposo y VFC si el reloj los registra; y las gráficas de carga y de horas por semana. Si se está descargando de Garmin, espera a que termine para que entren las actividades del domingo. Solo se hace si ha habido actividades en las cuatro semanas anteriores. **Rehacer el informe de la última semana** lo prepara de nuevo tras añadir actividades.
- **Informes, una entrada por semana:** la sección **Revisiones** desaparece. Cada informe se despliega con su título («Semana del 16/11/2026 al 22/11/2026»), el enlace al PDF, sus gráficas y, si los hay, el consejo y las revisiones propias de esa semana.
- **Inicio, Últimas notas:** sustituye a «Último consejo». Muestra la nota más reciente del Diario, con un enlace para seguir leyendo, y permite escribir una nota sin salir de Inicio. En la página Informes, «Notas» pasa a llamarse **Notas del Diario**.
- **Gráficas, eje vertical con decimales:** cuando el paso entre marcas no es entero (por ejemplo, el peso en 3 meses o las horas de sueño), las marcas llevan los decimales necesarios. Antes salían valores repetidos, como 87, 87, 87, 88.

## 3.54

- **VenB Rutas, varios clubes u organizadores:** en **Ajustes > Perfiles de club u organizador**, el alta va en su propio bloque, **Añadir un club u organizador**, con un botón destacado que despliega el formulario. Tras guardar un perfil, VenB recuerda que se pueden tener todos los que se necesiten; mientras editas uno, un enlace lleva al alta de otro. Al generar, el Planificador propone en cada ruta nueva el último club usado.
- **Quitar el fondo de los logotipos:** al subir un logotipo, la casilla **Quitar el fondo de color liso** vuelve transparente el fondo de un solo color (blanco u otro): toma el color de las esquinas y borra solo la zona unida a los bordes, así que el interior del dibujo del mismo color se conserva, y suaviza el contorno sin dejar halo. En los logotipos ya guardados, el botón **Quitar el fondo** hace lo mismo. Se ven sobre un fondo a cuadros, y **Recuperar el original** deshace el cambio. Si el fondo no es liso o ya es transparente, VenB lo avisa y no cambia nada.
- **Mapa «Juego de Tronos», título legible:** el título de la ruta y la línea de distancia y desnivel llevan un halo blanco, como los demás rótulos de ese mapa, para distinguirse del relieve. Los mapas Al-Ballut y personal no cambian.
- **Informe semanal:** lee el sueño y la VFC con el formato de las bases de garmindb 4.

## 3.53

- **Histórico, lista de actividades con scroll:** en **Análisis > Histórico**, la sección **Actividades** va en una caja con unas 15 actividades a la vista y scroll para ver las demás. Los títulos de las columnas quedan fijos al bajar.
- **Kilómetros acumulados, seis temporadas:** en **Todo tu histórico**, además de la temporada actual (azul) y la anterior (naranja), las cuatro previas, en grises cada vez más claros cuanto más antiguas y con su propia entrada en la leyenda. Cada línea termina con su total y, delante, el año y un punto de su color (por ejemplo, «2023 11.049»). Si dos totales coinciden, se apilan en lugar de ocultarse.

## 3.52

- **Datos de Garmin protegidos ante las actualizaciones de garmindb:** el programa que descarga los datos de Garmin (garmindb) cambió en su versión 4 el formato de sus bases de datos, y la instalación de la 3.50 lo actualizó sin adaptarlas. Desde entonces las descargas se cortaban a medias: llegaban las actividades y el sueño, pero no la FC en reposo ni la VFC, y las actividades nuevas no entraban en la base (perfiles y validación de sensores). Inicio solo decía «Comprueba que el reloj se ha sincronizado». Ahora:
  - VenB instala siempre la misma versión de garmindb, probada con VenB, en lugar de la última que haya.
  - VenB anota con qué versión de garmindb se crearon las bases. Si cambia, o si una descarga avisa de que el formato no coincide, las rehace con los datos ya descargados en el ordenador, sin pedir nada a Garmin Connect: al instalar o, si no, antes de la siguiente descarga. Tarda entre 10 y 30 minutos, solo esa vez, y guarda una copia de las bases anteriores.
  - Si se queda sin datos de salud recientes porque la descarga falla, Inicio dice el motivo real.
  - VenB lee el sueño y la VFC en el formato nuevo de garmindb (bases propias) y en el antiguo, y la copia de seguridad los incluye.
  - Si al instalar la 3.52 hay que rehacer las bases, el instalador lo avisa y tarda un poco más.
- **Mapas e infografía en A4:** la hoja es siempre un A4, vertical, u horizontal si el track es más ancho que alto. En los mapas personal y «Juego de Tronos», el perfil va dentro del A4: el mapa deja sitio para que quepan el título y el cartucho sin tapar el track, y el cartucho se reduce en proporción. En la infografía, el mapa se encuadra para el alto que dejan la cabecera, el perfil y el pie.
- **Servicios más visibles:** en los mapas y en la infografía, cada servicio junto al track es un disco de color con su icono en blanco (agua en azul, bar en marrón, tienda en verde, gasolinera en morado), mayor que antes, con una línea fina hasta el sitio real si hay que apartarlo. La leyenda lleva los iconos en su color.
- **Brevets, resumen de la ruta:** botón 📈 en cada fila del historial, como en el Histórico: distancia, tiempo, perfil y recorrido de la actividad enlazada (o la que VenB deduce por fecha y distancia).

## 3.51

- **Infografía en un solo mapa:** VenB procura que todos los puntos quepan en un mapa, reduciendo las cajas (hasta dos tercios) o haciendo el mapa más alto, en lugar de repartirlos en varias hojas de 9 en 9. Si aun así no caben, hace dos: ida y vuelta, cortando en el punto más alejado de la salida, cada una encuadrada en su parte. Un BRM 1000 que antes salía en 4 hojas, con días mezclados, sale ahora en una.
- **Cajas en el orden de la ruta:** en una ruta circular, las cajas la rodean por el borde del mapa en el sentido en que se recorre (horario o antihorario), y las líneas que las unen a sus puntos ya no se cruzan. Las etiquetas del perfil se reducen con las cajas.
- **Descargas de OpenStreetMap más rápidas y robustas:**
  - Se pide todo lo de cada zona en una sola consulta: unas 8 veces menos peticiones.
  - En rutas extensas (más de 200 km de lado, como un BRM 1000) no se descargan aldeas, cascos urbanos ni servicios, que no se distinguirían a esa escala, y ríos, cumbres y embalses solo junto al track: en un BRM 1000, 20 consultas en lugar de más de 200.
  - Si el servidor falla en una parte, se conserva el resto y el plan avisa de **Mapas incompletos**; al volver a generar, solo se pide lo que falta. Una respuesta cortada por el servidor ya no se guarda.
- **Comprobar el servidor de mapas:** botón junto a **Generar** que hace una consulta mínima y dice si OpenStreetMap responde bien, va lento o está saturado, para decidir si generar ahora o más tarde.
- **Detener proceso:** botón para parar un análisis o una generación en marcha (también si se lanzó desde otra ventana de VenB). Lo descargado se conserva. Barra de avance con el tiempo que queda al descargar datos de OpenStreetMap, del IGN y teselas, y aviso de que con el servidor saturado puede pasar de una hora.
- **Ficheros generados** en dos columnas: la ruta con waypoints (GPX) a la izquierda; la tabla de tiempos y la página interactiva a la derecha.

## 3.50

- **Planificador, análisis con reloj:** mientras se analiza una ruta se ven el tiempo transcurrido, el paso en curso y, al consultar las altitudes del terreno, el lote y lo que queda (un BRM 1000 tarda unos 5 minutos; el servicio público de altitudes no admite más de una consulta por segundo).
- **Ruta para una web:** con la página interactiva generada, un ZIP para publicarla en tu web o en la de tu club: una carpeta con `index.html` (lo lleva todo dentro) y un LEEME con los pasos. **Como ficha de ruta**, con los tiempos desde la salida («+2:15») y sin fecha, cierres ni márgenes; o **con horario**. VenB muestra el código para insertarla en una página (en WordPress, bloque «HTML personalizado»); con la dirección de tu web en **Ajustes > Planificador**, sale ya completo. El manual explica cómo publicarla.
- **Mapas dibujados más fieles:** cada pueblo se dibuja sobre su casco urbano (zonas residenciales de OpenStreetMap), no en un hueco cualquiera junto al nombre, y un pueblo sin casco cerca no se dibuja; las aldeas y cortijadas junto a la ruta llevan unas casitas; los árboles sueltos van solo donde OpenStreetMap tiene bosque.
- **Servicios junto al track:** casilla **Marcar servicios junto al track** al generar. Los mapas Al-Ballut y personal y las infografías con mapa del IGN señalan fuentes 🚰, bares y restaurantes ☕, tiendas 🛒 y gasolineras ⛽ a menos de 400 m del track, como mucho uno de cada tipo cada pocos km; dentro de los pueblos, solo los supermercados de cadena. Con su leyenda al pie.
- Corregido: si VenB se cerraba y se volvía a abrir durante una generación larga (o había otra VenB abierta sobre los mismos datos), la página decía «El proceso se interrumpió» aunque seguía trabajando, y al pulsar Generar respondía «Este plan ya se está procesando» sin mostrar nada. Ahora el proceso deja una señal de vida cada pocos segundos: mientras siga trabajando, la página lo sabe y muestra el reloj y el paso en curso.
- Incluye también lo de la [3.47](https://github.com/jj99211/VenB/releases/tag/v3.47): explicación y botón para la velocidad calculada desde la llegada prevista de las etapas, y el calendario que se cerraba al cambiar de mes.

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
