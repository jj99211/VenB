# Instalar y actualizar VenB

VenB (Vivir en Bici) sigue tu entrenamiento de ciclismo, tus bicis, tus brevets y tu calendario, y planifica rutas. Funciona en tu ordenador, con Windows o Linux: se abre en el navegador y tus datos no salen de él. Es libre y gratuita (licencia Creative Commons BY-NC-SA 4.0).

## Qué necesitas

- Un ordenador con **Windows 10 u 11** o **Linux**, y conexión a internet durante la instalación.
- **Python 3.10 o posterior**. Si no lo tienes, el instalador de VenB lo detecta y te ayuda: en Windows ofrece instalarlo en ese momento (responde `S`); en Linux muestra la orden exacta para tu distribución, por ejemplo `sudo apt install python3 python3-venv python3-pip curl` en Ubuntu, Linux Mint o Debian.

## Descargar

Las versiones se publican en GitHub, en la página de descargas de VenB:

**[https://github.com/jj99211/VenB/releases/latest](https://github.com/jj99211/VenB/releases/latest)**

En el apartado **Assets** de la última versión, descarga **VenB-X.YZ.zip** (X.YZ es el número de versión). El otro ZIP, VenB-X.YZ-Rutas.zip, es VenB Rutas: solo el Planificador de rutas, para clubes y organizadores.

## Instalar

1. **Descomprime el ZIP** donde quieras, por ejemplo en Descargas. En Windows: botón derecho sobre el ZIP > **Extraer todo** > **Extraer**. No ejecutes el instalador desde dentro del ZIP sin extraerlo.
2. **Ejecuta el instalador** de la carpeta extraída:
    - **Windows**: doble clic en **INSTALAR-EN-WINDOWS**. Si Windows muestra «Windows protegió su PC», pulsa **Más información** > **Ejecutar de todas formas**.
    - **Linux**: abre una terminal en esa carpeta y escribe `bash instalar-en-linux.sh`.
3. **Elige la carpeta.** La primera vez propone `Documentos\VenB` (Windows) o `~/VenB` (Linux): pulsa Intro para aceptar o escribe otra. Allí quedan el programa (carpeta `VenB-X.YZ`) y, a su lado, **`VenB-datos`**, con tus datos y tu configuración.
4. El instalador descarga lo que necesita (unos minutos la primera vez), crea el icono de VenB en el escritorio y pregunta si quieres instalar la descarga automática de Garmin Connect (en Linux, también el aviso semanal). Si no usas Garmin, responde que no: puedes importar ficheros GPX, FIT o TCX.
5. Al terminar, puedes borrar el ZIP y la carpeta extraída.

## Abrir y cerrar

Abre VenB con su icono. Se abre una ventana de terminal, que debe quedarse abierta mientras uses VenB, y el navegador en `http://127.0.0.1:8877`. Para cerrarla, usa el botón **Cerrar VenB** de la aplicación o pulsa Ctrl+C en la terminal.

La **Ayuda** de la aplicación explica cada página; el manual de usuario completo está también en la página de descargas.

## Actualizar

VenB busca versiones nuevas en GitHub al abrirse (y cada pocas horas mientras está abierta). Cuando hay una, lo avisa en **Inicio**:

1. Pulsa **Actualizar ahora**. El enlace **Novedades** muestra qué cambia.
2. VenB descarga la versión nueva, comprueba que el fichero es el publicado y se cierra.
3. El instalador de la versión nueva se ejecuta solo en la terminal (en Windows, en una ventana nueva), sin preguntas: copia el programa junto a tus datos, actualiza el icono y borra la versión anterior.
4. VenB se vuelve a abrir con la versión nueva, y la pestaña del navegador se recarga sola. Suele tardar uno o dos minutos.

También puedes buscar versiones en **Ayuda > Acerca de** con **Buscar ahora**.

**Tus datos no se tocan**: están en `VenB-datos`, que ningún ZIP contiene. Si una actualización falla, la versión anterior sigue instalada: ábrela con su icono y, si quieres, actualiza a mano.

### Actualizar a mano

Descarga el ZIP nuevo, descomprímelo donde quieras y ejecuta su instalador, como al instalar. El instalador encuentra tu instalación y tus datos, te dice qué contienen y copia allí la versión nueva.

### Si tienes la versión 3.39 o anterior

Esas versiones buscaban las actualizaciones en Google Drive y no tienen el botón **Actualizar ahora**. Instala la versión nueva a mano, una sola vez, como se explica arriba: tus datos se conservan. A partir de ahí, las actualizaciones llegan desde GitHub con el botón.

## Copia de seguridad

En **Ajustes > Copia de seguridad**, **Exportar** guarda en un solo fichero tus datos de VenB y lo descargado de Garmin. Guárdalo fuera del ordenador de vez en cuando. **Importar** lo restaura, también en otro ordenador después de instalar VenB.

## Si algo falla

- **Falta Python o es antiguo.** El instalador lo dice. En Windows, si después de instalarlo sigue sin encontrarlo, cierra la ventana y vuelve a ejecutar INSTALAR-EN-WINDOWS.
- **Al escribir `python` se abre la Microsoft Store.** Desactiva los alias de `python.exe` y `python3.exe` en **Configuración > Aplicaciones > Configuración avanzada de aplicaciones > Alias de ejecución de aplicaciones**.
- **El navegador no abre VenB.** Comprueba que la terminal sigue abierta y escribe en el navegador `http://127.0.0.1:8877`.
- **Otra duda o un error**: escribe a [jj99211@gmail.com](mailto:jj99211@gmail.com) con tu sistema (Windows o Linux), la versión de VenB y, si puedes, una captura de la terminal.
