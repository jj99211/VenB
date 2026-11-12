"""Primer paso de los instaladores: decide dónde queda instalada VenB, sea cual sea la carpeta donde se descomprimió.
Lo ejecutan instalar-en-linux.sh e INSTALAR-EN-WINDOWS.bat con el Python del sistema (solo biblioteca estándar).

Orden para encontrar la carpeta base (la que contiene VenB-datos y las versiones VenB-X.YZ):
  1. La anotada por la instalación anterior en ~/.venb/instalacion.json (en Windows, %USERPROFILE%\\.venb), si su
     VenB-datos sigue allí.
  2. La del icono de VenB (escritorio o menú), que apunta a la versión instalada: así se encuentran las instalaciones
     anteriores a la 3.34, que no anotaban nada, aunque el ZIP nuevo se haya descomprimido en otro sitio.
  3. La carpeta donde se descomprimió el ZIP, si tiene VenB-datos al lado.
  4. Si ~/.venb ya existe (VenB estuvo instalada) pero no aparecen los datos, pregunta dónde están.
  5. Primera instalación: propone Documentos\\VenB (Windows) o ~/VenB (Linux); Intro acepta.
Si la carpeta anotada ya no tiene VenB-datos, no se crea otra vacía sin preguntar.
Después copia el programa a <base>/VenB-X.YZ (si no está ya allí), marca VenB-datos con .venb-datos (identidad)
y anota la base. Escribe la carpeta del programa instalado en el fichero indicado con --salida.
Uso: python3 ubicar.py --salida FICHERO [--base CARPETA]
Con --base (el botón «Actualizar» de VenB) se usa esa carpeta sin preguntar nada, si tiene VenB-datos.
VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0."""
import argparse
import csv
import json
import os
import re
import shutil
import sys
from datetime import datetime

ORIGEN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # carpeta descomprimida
INTERNO = os.path.join(os.path.expanduser('~'), '.venb')
ANOTACION = os.path.join(INTERNO, 'instalacion.json')
DATOS = 'VenB-datos'
# VenB Rutas (su ZIP lleva venb/EDICION) se copia a VenB-Rutas-X.YZ, junto a VenB completo si lo hay, con los mismos datos
PREFIJO = 'VenB-Rutas-' if os.path.exists(os.path.join(ORIGEN, 'venb', 'EDICION')) else 'VenB-'
IDENTIDAD = '.venb-datos'


def documentos():
    """Carpeta Documentos del usuario (en Windows puede estar en OneDrive u otra unidad)."""
    if os.name == 'nt':
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return buf.value
        except Exception:
            pass
        return os.path.join(os.path.expanduser('~'), 'Documents')
    return os.path.expanduser('~')


def es_datos(ruta):
    """¿Es una carpeta de datos de VenB? (su marca de identidad o, en las antiguas, su estructura)."""
    return os.path.isdir(ruta) and (os.path.exists(os.path.join(ruta, IDENTIDAD))
                                    or os.path.isdir(os.path.join(ruta, 'config')) and os.path.isdir(os.path.join(ruta, 'datos')))


def anotada():
    try:
        with open(ANOTACION, encoding='utf-8') as f:
            return json.load(f).get('base') or None
    except (OSError, ValueError):
        return None


def por_icono():
    """Carpetas base deducidas de los iconos de VenB que dejó el instalador (la carpeta de la versión, su padre)."""
    destinos = []
    if os.name == 'nt':
        try:
            import subprocess
            orden = ("$s=New-Object -ComObject WScript.Shell; foreach($d in @([Environment]::GetFolderPath('Desktop'),"
                     "[Environment]::GetFolderPath('CommonDesktopDirectory'))){ $l=Join-Path $d 'VenB.lnk';"
                     " if(Test-Path $l){ $s.CreateShortcut($l).TargetPath } }")
            r = subprocess.run(['powershell', '-NoProfile', '-Command', orden], capture_output=True, text=True, timeout=30)
            destinos = [x.strip() for x in r.stdout.splitlines() if x.strip()]
        except Exception:
            pass
    else:
        import glob
        for f in glob.glob(os.path.expanduser('~/.local/share/applications/VenB*.desktop')) + glob.glob(os.path.expanduser('~/*/VenB.desktop')):
            try:
                with open(f, encoding='utf-8') as h:
                    destinos += re.findall(r'^Exec=.*?"([^"]+venb\.sh)"', h.read(), re.M)
            except OSError:
                pass
    # .../VenB-X.YZ/venb/venb.bat (o venb.sh) -> .../  (la carpeta que contiene VenB-X.YZ y VenB-datos)
    return [os.path.dirname(os.path.dirname(os.path.dirname(d))) for d in destinos]


def version():
    with open(os.path.join(ORIGEN, 'venb', 'VERSION'), encoding='utf-8') as f:
        v = f.read().strip()
    if not re.fullmatch(r'\d+\.\d+', v):
        sys.exit(f'Versión no reconocida: {v}')
    return v


def preguntar(texto):
    try:
        return input(texto).strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        sys.exit('\nInstalación cancelada: no se ha cambiado nada.')


def resumen(datos):
    """Una línea con lo que hay en VenB-datos, para que el usuario reconozca sus datos."""
    partes = []
    for nombre, fichero in (('brevets', 'brevets.csv'), ('actividades subidas a mano', 'actividades_locales.csv'),
                            ('notas del diario', 'diario.csv')):
        try:
            with open(os.path.join(datos, 'datos', fichero), encoding='utf-8') as f:
                n = sum(1 for _ in csv.reader(f)) - 1
            if n > 0:
                partes.append(f'{n} {nombre}')
        except OSError:
            pass
    if os.path.exists(os.path.join(datos, 'datos', 'historico_actividades.csv')):
        partes.append('historial de Garmin')
    return ', '.join(partes) if partes else 'todavía sin datos propios'


def elegir_base():
    """(base, nueva): carpeta base y si los datos se van a crear ahora."""
    previa = anotada()
    if previa and es_datos(os.path.join(previa, DATOS)):
        return previa, False
    for base in por_icono():
        if es_datos(os.path.join(base, DATOS)):
            return base, False
    junto = os.path.dirname(ORIGEN)
    if es_datos(os.path.join(junto, DATOS)):
        return junto, False
    if not previa and os.path.isdir(os.path.join(INTERNO, 'python')):     # VenB estuvo instalada, sin anotación
        print('\nVenB ya estuvo instalada en este ordenador, pero no encuentro tu carpeta de datos (VenB-datos).')
        print('Escribe dónde está (la propia VenB-datos o la carpeta que la contiene). Suele estar junto a las carpetas VenB-X.YZ.')
        previa = '?'
    if previa:
        if previa != '?':
            print(f'\nLa instalación anterior tenía los datos en {os.path.join(previa, DATOS)}, pero esa carpeta ya no está.')
            print('Si la has movido, escribe dónde está ahora la carpeta VenB-datos (o la carpeta que la contiene).')
        while True:
            r = preguntar('Carpeta de VenB-datos (o escribe NUEVA para empezar sin datos): ')
            if r.upper() == 'NUEVA':
                break
            r = os.path.abspath(os.path.expanduser(r)) if r else ''
            for base in (os.path.dirname(r), r):
                if r and es_datos(os.path.join(base, DATOS)):
                    return base, False
            if r and es_datos(r):
                print('Esa carpeta parece de datos de VenB, pero tiene que llamarse VenB-datos: cámbiale el nombre y repite.')
            else:
                print('Ahí no hay una carpeta VenB-datos. Prueba otra vez.')
    defecto = os.path.join(documentos(), 'VenB')
    print('\nPrimera instalación de VenB en este ordenador.')
    print(f'Se instalará en {defecto}, con tus datos en {os.path.join(defecto, DATOS)}.')
    while True:
        r = preguntar('Pulsa Intro para aceptar o escribe otra carpeta: ')
        base = os.path.abspath(os.path.expanduser(r)) if r else defecto
        if os.path.basename(base) == DATOS:          # ha escrito la propia carpeta de datos
            base = os.path.dirname(base)
        # dentro de la carpeta descomprimida, la copia se metería en sí misma
        if os.path.normcase(base + os.sep).startswith(os.path.normcase(ORIGEN + os.sep)):
            print(f'Esa carpeta está dentro de la que has descomprimido ({ORIGEN}). Escribe la ruta completa de otra, por ejemplo {defecto}.')
            continue
        return base, not es_datos(os.path.join(base, DATOS))


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--salida', required=True)
    a.add_argument('--base')
    o = a.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
    v = version()
    if o.base:
        if not es_datos(os.path.join(o.base, DATOS)):
            sys.exit(f'No se encuentra la carpeta de datos {os.path.join(o.base, DATOS)}: no se ha cambiado nada.')
        base, nueva = os.path.abspath(o.base), False
    else:
        base, nueva = elegir_base()
    datos = os.path.join(base, DATOS)
    destino = os.path.join(base, f'{PREFIJO}{v}')
    os.makedirs(datos, exist_ok=True)
    if not os.path.exists(os.path.join(datos, IDENTIDAD)):
        with open(os.path.join(datos, IDENTIDAD), 'w', encoding='utf-8') as f:
            f.write(f'Carpeta de datos de VenB (marcada el {datetime.now():%d/%m/%Y}). No la borres: aquí están tus datos.\n')
    print(f'\nTus datos: {datos}' + ('' if nueva else f' ({resumen(datos)}).'))
    if os.path.normcase(os.path.abspath(destino)) != os.path.normcase(ORIGEN):
        print(f'Copiando VenB {v} a {destino}...')
        shutil.copytree(ORIGEN, destino, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    os.makedirs(INTERNO, exist_ok=True)
    with open(ANOTACION, 'w', encoding='utf-8') as f:
        json.dump({'base': base, 'version': v, 'fecha': datetime.now().isoformat(timespec='seconds')}, f, ensure_ascii=False, indent=1)
    with open(o.salida, 'w', encoding='utf-8') as f:
        f.write(destino)


if __name__ == '__main__':
    main()
