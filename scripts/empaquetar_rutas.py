"""ZIP de VenB Rutas, la edición solo con el Planificador para clubes y organizadores, con el MISMO número de versión
que VenB: parte de la misma etiqueta y el mismo código (un solo repositorio; los cambios del motor de mapas llegan a las
dos ediciones a la vez). Lo llama empaquetar.py al terminar el ZIP normal; también se puede ejecutar solo.
Diferencias con VenB completo, todas en tiempo de ejecución según el fichero venb/EDICION («rutas»):
  - menú con Planificador, Ajustes y Ayuda (el capítulo del Planificador); el resto de páginas no existe;
  - perfiles de club en Ajustes (venb/clubes.py) y elección del club al generar; la marca de VenB va siempre al lado;
  - el instalador copia el programa a VenB-Rutas-X.YZ (convive con VenB-X.YZ y comparte VenB-datos), con su propio
    icono y sin aviso semanal ni descarga de Garmin;
  - el botón «Actualizar» busca VenB-X.YZ-Rutas.zip en la misma versión publicada en GitHub que VenB;
  - usa su propio puerto (`puerto_rutas`, 8878), para poder estar abierta a la vez que VenB.
Deja VenB-X.YZ-Rutas.zip junto al repositorio y borra los de versiones anteriores.
VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0."""
import glob
import hashlib
import io
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from empaquetar import RAIZ, git  # noqa: E402

SUFIJO = 'Rutas'
LEEME = '''VenB Rutas (Vivir en Bici)
Autor: José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0 (venb/LICENSE.md), que incluye el logotipo de VenB.
Soporte: jj99211@gmail.com
Descargas, novedades y guía de instalación: https://github.com/jj99211/VenB/releases/latest

VenB Rutas es la edición de VenB para clubes y organizadores: solo el Planificador de rutas. A partir del track (GPX) y,
si la hay, la hoja de ruta de una prueba, calcula los horarios de paso y los cierres de cada control y genera la tabla de
tiempos, infografías, mapas ilustrados, una página interactiva y el track con waypoints para Garmin y otros GPS.
Los documentos llevan la marca del club que elijas y, siempre, la de VenB.
Tiene el mismo número de versión que VenB, que incluye además entrenamiento, bicis, brevets y calendario.

INSTALAR (o actualizar), con internet:
- WINDOWS: primero extrae el ZIP (botón derecho > Extraer todo). Luego, doble clic en INSTALAR-EN-WINDOWS.
- LINUX: en una terminal abierta en esta carpeta, bash instalar-en-linux.sh
Hace falta Python 3.10 o posterior. Si falta, el instalador lo dice y ayuda a instalarlo.

La primera vez, el instalador propone instalar en Documentos\\VenB (Windows) o ~/VenB (Linux); pulsa Intro para aceptar.
Allí quedan el programa (VenB-Rutas-X.YZ) y, a su lado, VenB-datos, con tus rutas, tus perfiles de club y tu configuración.
Ningún ZIP la contiene, así que una versión nueva no la sobrescribe. Si ya tienes VenB instalada, VenB Rutas se instala
a su lado y comparte VenB-datos. Al terminar, puedes borrar el ZIP y la carpeta donde lo descomprimiste.

EMPEZAR
1. Ajustes > Perfiles de club u organizador: crea el perfil de tu club con su nombre, su web y uno o varios logotipos
   (mejor PNG con fondo transparente).
2. Planificador: sube el track y la hoja de ruta, revisa los puntos y los tiempos y, en Documentos, elige el club y
   pulsa Generar. La primera vez en una zona nueva puede tardar de 10 a 15 minutos (se descargan mapas y datos).
La Ayuda de la aplicación explica el Planificador paso a paso.

ACTUALIZAR
VenB Rutas busca versiones nuevas en GitHub y lo avisa en el Planificador. Pulsa «Actualizar ahora»: descarga la versión
nueva, se cierra, la instala junto a tus datos (sin preguntas) y se vuelve a abrir. También en Ayuda > Acerca de.
A mano: cierra la aplicación, descomprime el ZIP nuevo donde quieras y ejecuta su instalador. Desde la 3.39 o anteriores
(sin el botón), actualiza así una vez. Si usabas la edición de Randonneurs Andalucía, instala VenB Rutas: usa tus mismos
datos; crea en Ajustes el perfil del club con su logotipo y borra a mano la carpeta y el icono de la edición anterior.

ABRIR Y CERRAR
Usa el icono de VenB Rutas. Se abre una terminal que espera mientras la aplicación está abierta, y el navegador en
http://127.0.0.1:8878.
Para cerrarla, usa el botón «Cerrar VenB» o pulsa Ctrl+C en la terminal.
'''


def empaquetar(version=None):
    version = version or git('describe', '--tags', '--abbrev=0').removeprefix('v')
    if not re.fullmatch(r'\d+\.\d{2}', version):
        sys.exit(f'La versión {version} no es una etiqueta vX.YZ.')
    pref = f'VenB-Rutas-{version}/'
    carpeta = os.path.dirname(RAIZ)
    destino = os.path.join(carpeta, f'VenB-{version}-{SUFIJO}.zip')
    base = zipfile.ZipFile(io.BytesIO(git('archive', '--format=zip', f'--prefix={pref}', f'v{version}', binario=True)))
    with zipfile.ZipFile(destino, 'w', zipfile.ZIP_DEFLATED) as z:
        for i in base.infolist():
            if i.is_dir():
                continue
            rel = i.filename[len(pref):]
            datos = base.read(i.filename)
            i.create_system = 3
            i.external_attr = (0o755 if i.filename.endswith('.sh') else 0o644) << 16
            if rel == 'config/predeterminados.json':
                c = json.loads(datos)
                c['usar_garmin'] = False
                datos = (json.dumps(c, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
            elif rel == 'LEEME.txt':
                datos = LEEME.encode('utf-8')
            z.writestr(i, datos)
        z.writestr(f'{pref}venb/EDICION', 'rutas\n')
        z.writestr(f'{pref}venb/VERSION', version + '\n')
    with zipfile.ZipFile(destino) as z:
        lineas = [f'{hashlib.sha256(z.read(n)).hexdigest()}  {n[len(pref):]}' for n in z.namelist() if not n.endswith('/')]
    with zipfile.ZipFile(destino, 'a', zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'{pref}MANIFIESTO.txt', '\n'.join(lineas) + '\n')
    for viejo in glob.glob(os.path.join(carpeta, f'VenB-*-{SUFIJO}.zip')):
        if os.path.abspath(viejo) != os.path.abspath(destino):
            os.remove(viejo)
    return destino


if __name__ == '__main__':
    print(empaquetar())
