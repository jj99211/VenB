# Instalar y actualizar VenB Rutas

VenB Rutas es la edición de VenB (Vivir en Bici) para clubes y organizadores: solo el **Planificador de rutas**. A partir del track (GPX) y, si la hay, la hoja de ruta de una prueba, calcula los horarios de paso y los cierres de cada control y genera la tabla de tiempos, infografías, mapas ilustrados, una página interactiva y el track con waypoints para Garmin y otros GPS, con la marca de tu club. Funciona en tu ordenador, con Windows o Linux. Es libre y gratuita (licencia Creative Commons BY-NC-SA 4.0).

## Qué necesitas

- Un ordenador con **Windows 10 u 11** o **Linux**, y conexión a internet (para instalar y para descargar mapas y datos del terreno).
- **Python 3.10 o posterior**. El instalador de VenB lo comprueba y, si falta o es antiguo, ayuda a instalarlo; el apartado siguiente explica cómo hacerlo a mano.

## Python: comprobarlo e instalarlo

VenB está escrito en Python y necesita **Python 3.10 o posterior** en el ordenador. Python es libre y gratuito, y solo se instala una vez: las versiones nuevas de VenB lo siguen usando. El instalador de VenB comprueba si está y, si falta o es antiguo, avisa y ayuda a instalarlo: en Windows ofrece instalar Python en ese momento (responde `S` y sigue solo; si no puede, abre la página de descarga) y en Linux muestra la orden exacta para tu distribución. Si prefieres hacerlo a mano, sigue estos pasos.

### Comprobar si ya lo tienes

- **Windows**: pulsa la tecla Windows, escribe `cmd` y pulsa Intro. En la ventana negra escribe `py --version` y pulsa Intro.
- **Linux**: abre una terminal y escribe `python3 --version`.

Si responde `Python 3.10` o un número mayor (por ejemplo, `Python 3.15.2`), ya lo tienes: pasa a «Descargar». Si dice que no reconoce la orden, o la versión es menor, sigue leyendo.

### Windows

1. Entra en [https://www.python.org/downloads/](https://www.python.org/downloads/) y pulsa el botón **Download Python** de la versión más reciente. Descárgalo solo de esa web oficial.
2. Abre el fichero descargado. Según la versión, será el **instalador de Python** o el **Python install manager** (administrador de instalaciones). Los dos sirven.
3. Con el **instalador de Python**, antes de nada marca abajo la casilla **Add python.exe to PATH** y pulsa **Install Now**. Si al final aparece **Disable path length limit**, púlsalo también.
4. Con el **Python install manager**, acepta lo que propone. Si pregunta si quieres instalar ya la última versión de Python, responde que sí (`Y` e Intro).
5. Cierra todas las ventanas de `cmd` abiertas, abre una nueva y comprueba la versión con `py --version`.

### Linux

Casi todas las distribuciones traen Python 3. Aun así, conviene asegurarse de que están el módulo para crear entornos (`venv`), `pip` y `curl`, que el instalador de VenB usa para descargar sus componentes. En una terminal, según tu distribución:

| Distribución | Orden |
|---|---|
| Ubuntu, Linux Mint, Debian | `sudo apt install python3 python3-venv python3-pip curl` |
| Fedora | `sudo dnf install python3 python3-pip curl` |
| openSUSE | `sudo zypper install python3 python3-pip curl` |
| Arch, Manjaro | `sudo pacman -S python python-pip curl` |

Te pedirá tu contraseña. Si tu distribución es antigua y trae una versión de Python menor que la 3.10 (por ejemplo, Ubuntu 20.04), lo más sencillo es actualizar la distribución.


### Si algo falla

- **Windows dice que falta Python aunque lo has instalado.** Seguramente no se marcó **Add python.exe to PATH**. Vuelve a abrir el instalador de Python, elige **Modify**, pulsa **Next**, marca **Add Python to environment variables** y pulsa **Install**. Después, cierra y vuelve a abrir la ventana.
- **Al escribir `python` se abre la Microsoft Store.** Windows trae un acceso directo que suplanta a Python. Desactívalo en **Configuración → Aplicaciones → Configuración avanzada de aplicaciones → Alias de ejecución de aplicaciones**, apagando los de `python.exe` y `python3.exe`.
- **En Linux, el instalador de VenB falla al crear el entorno.** Instala los paquetes de la tabla anterior (sobre todo `python3-venv` y `curl`) y repítelo.
- **La versión es menor que la 3.10.** Instala la más reciente desde python.org (Windows) o actualiza la distribución (Linux).

## Descargar

Las versiones se publican en GitHub, en la página de descargas de VenB:

**[https://github.com/jj99211/VenB/releases/latest](https://github.com/jj99211/VenB/releases/latest)**

En el apartado **Assets** de la última versión, descarga **VenB-X.YZ-Rutas.zip** (X.YZ es el número de versión). El otro ZIP, VenB-X.YZ.zip, es VenB completo, con entrenamiento, bicis, brevets y calendario.

## Instalar

1. **Descomprime el ZIP** donde quieras, por ejemplo en Descargas. En Windows: botón derecho sobre el ZIP > **Extraer todo** > **Extraer**. No ejecutes el instalador desde dentro del ZIP sin extraerlo.
2. **Ejecuta el instalador** de la carpeta extraída:
    - **Windows**: doble clic en **INSTALAR-EN-WINDOWS**. Si Windows muestra «Windows protegió su PC», pulsa **Más información** > **Ejecutar de todas formas**.
    - **Linux**: abre una terminal en esa carpeta y escribe `bash instalar-en-linux.sh`.
3. **Elige la carpeta.** La primera vez propone `Documentos\VenB` (Windows) o `~/VenB` (Linux): pulsa Intro para aceptar o escribe otra. Allí quedan el programa (carpeta `VenB-Rutas-X.YZ`) y, a su lado, **`VenB-datos`**, con tus rutas, tus perfiles de club y tu configuración.
4. El instalador descarga lo que necesita (unos minutos la primera vez) y crea el icono **VenB Rutas** en el escritorio.
5. Al terminar, puedes borrar el ZIP y la carpeta extraída.

**Si ya tienes VenB completo**, VenB Rutas se instala a su lado y comparte `VenB-datos`: las rutas del Planificador son las mismas en las dos. Pueden estar abiertas a la vez.

## Abrir, cerrar y empezar

Abre VenB Rutas con su icono. Se abre una ventana de terminal, que debe quedarse abierta mientras la uses, y el navegador en `http://127.0.0.1:8878`. Para cerrarla, usa el botón **Cerrar VenB** o pulsa Ctrl+C en la terminal.

1. **Ajustes > Perfiles de club u organizador**: crea el perfil de tu club con su nombre, su web y hasta cuatro logotipos (mejor PNG con fondo transparente).
2. **Planificador**: sube el track y la hoja de ruta, revisa los puntos y los tiempos y, en Documentos, elige el club y pulsa **Generar**. La primera vez en una zona nueva puede tardar de 10 a 15 minutos (se descargan mapas y datos); después, segundos.

La **Ayuda** de la aplicación explica el Planificador paso a paso.

## Actualizar

VenB Rutas busca versiones nuevas en GitHub al abrirse (y cada pocas horas mientras está abierta). Cuando hay una, lo avisa en la página del **Planificador**:

1. Pulsa **Actualizar ahora**. El enlace **Novedades** muestra qué cambia.
2. VenB Rutas descarga la versión nueva, comprueba que el fichero es el publicado y se cierra.
3. El instalador de la versión nueva se ejecuta solo en la terminal (en Windows, en una ventana nueva), sin preguntas: copia el programa junto a tus datos, actualiza el icono y borra la versión anterior.
4. VenB Rutas se vuelve a abrir con la versión nueva, y la pestaña del navegador se recarga sola. Suele tardar uno o dos minutos.

También puedes buscar versiones en **Ayuda > Acerca de** con **Buscar ahora**. **Tus rutas y perfiles no se tocan**: están en `VenB-datos`, que ningún ZIP contiene.

Para actualizar a mano, descarga el ZIP nuevo, descomprímelo y ejecuta su instalador, como al instalar: encuentra tu instalación y tus datos.

### Si usabas la edición de Randonneurs Andalucía o VenB Rutas 3.39

Esas versiones buscaban las actualizaciones en Google Drive y no tienen el botón **Actualizar ahora**. Instala VenB Rutas a mano una sola vez, como se explica arriba:

- El instalador encuentra tu instalación anterior y usa la misma carpeta `VenB-datos`: tus rutas aparecen solas. Por precaución, antes puedes guardar una copia en **Ajustes > Copia de seguridad > Exportar**.
- La marca de la edición de Randonneurs Andalucía iba dentro del programa: en VenB Rutas, crea el perfil del club con su logotipo (paso 1 de «Abrir, cerrar y empezar») y elígelo al generar.
- Si venías de la edición de Randonneurs Andalucía, borra a mano su carpeta (`VenB-X.YZ`, junto a `VenB-datos`) y su icono: el instalador de VenB Rutas no los toca, porque son de otra edición. **No borres `VenB-datos`.**

## Copia de seguridad

En **Ajustes > Copia de seguridad**, **Exportar** guarda en un solo fichero tus rutas, tus perfiles de club y tu configuración. Guárdalo fuera del ordenador de vez en cuando. **Importar** lo restaura, también en otro ordenador después de instalar VenB Rutas.

## Otros problemas

- **El navegador no abre VenB Rutas.** Comprueba que la terminal sigue abierta y escribe en el navegador `http://127.0.0.1:8878`.
- **Otra duda o un error**: escribe a [jj99211@gmail.com](mailto:jj99211@gmail.com) con tu sistema (Windows o Linux), la versión y, si puedes, una captura de la terminal.
