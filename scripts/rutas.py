"""Dónde viven los datos y la configuración de VenB: en la carpeta VenB-datos, fuera del programa.
Cada versión instalada (VenB-X.YZ) la encuentra a su lado. Una copia de desarrollo en otra carpeta puede
localizarla con el fichero .ruta_datos. Ningún ZIP normal la contiene, así que instalar no puede sobrescribirla.
Los valores por defecto están en config/predeterminados.json; los del usuario, en VenB-datos/config/ajustes.json.
Lo interno va en una sola carpeta oculta, ~/.venb, fuera de las copias de seguridad: los entornos de Python (python/),
la configuración y la sesión de garmindb (garmin/) y los datos que descarga (HealthData/). La dirección del calendario propio
es de cada instalación: VenB-datos/config/calendario_url.txt (entre la 2.10 y la 3.03 estuvo en ~/.venb)."""
import json
import os
import shutil

PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _edicion():
    """'rutas' en VenB Rutas (solo el Planificador): su ZIP lleva venb/EDICION. '' en VenB completo."""
    try:
        with open(os.path.join(PROYECTO, 'venb', 'EDICION'), encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


EDICION = _edicion()
RUTAS = EDICION == 'rutas'
# Carpeta del programa: VenB-X.YZ o, en VenB Rutas, VenB-Rutas-X.YZ (pueden convivir junto a la misma VenB-datos)
PREFIJO_CARPETA = 'VenB-Rutas-' if RUTAS else 'VenB-'
NOMBRE = 'VenB-datos'
PREDETERMINADOS = os.path.join(PROYECTO, 'config', 'predeterminados.json')


def _buscar():
    puntero = os.path.join(PROYECTO, '.ruta_datos')
    if os.path.exists(puntero):
        with open(puntero, encoding='utf-8') as f:
            return f.read().strip()
    return os.path.join(os.path.dirname(PROYECTO), NOMBRE)


PERSISTE = _buscar()
CONFIG = os.path.join(PERSISTE, 'config')
DATOS = os.path.join(PERSISTE, 'datos')
INFORMES = os.path.join(PERSISTE, 'informes')
ESTADO = os.path.join(PERSISTE, 'estado')
INTERNO = SECRETOS = os.path.join(os.path.expanduser('~'), '.venb')
GARMIN_CONFIG = os.path.join(INTERNO, 'garmin')  # se pasa a garmindb con -f
BASE_HEALTHDATA = '.venb/HealthData'  # base_dir de garmindb, relativo a la carpeta personal


def python_venv(nombre):
    """Python del entorno ~/.venb/python/NOMBRE (venb o garmindb)."""
    base = os.path.join(INTERNO, 'python', nombre)
    return os.path.join(base, 'Scripts', 'python.exe') if os.name == 'nt' else os.path.join(base, 'bin', 'python')
AVISOS = os.path.join(CONFIG, 'avisos.json')
AJUSTES = os.path.join(CONFIG, 'ajustes.json')
CAL_URL = os.path.join(CONFIG, 'calendario_url.txt')
for _d in (CONFIG, DATOS, INFORMES, ESTADO):
    os.makedirs(_d, exist_ok=True)


def _mover_calendario():
    """Entre la 2.10 y la 3.03, la dirección del calendario estaba en ~/.venb, compartida por todas las instalaciones."""
    viejo = os.path.join(SECRETOS, 'calendario_url.txt')
    if not os.path.exists(viejo):
        return
    if os.path.exists(CAL_URL):
        os.remove(viejo)
    else:
        shutil.move(viejo, CAL_URL)
    try:
        os.chmod(CAL_URL, 0o600)
    except OSError:
        pass


_mover_calendario()


def ajustes():
    """Valores por defecto del programa, con los del usuario por encima."""
    with open(PREDETERMINADOS, encoding='utf-8') as f:
        valores = json.load(f)
    if os.path.exists(AJUSTES):
        with open(AJUSTES, encoding='utf-8') as f:
            valores.update(json.load(f))
    return valores


def puerto():
    """Puerto de esta edición: VenB y VenB Rutas usan puertos distintos para poder estar abiertas a la vez
    (`puerto` y `puerto_rutas`; ajustes.json es compartido por las dos)."""
    a = ajustes()
    return int(a.get('puerto_rutas', 8878) if RUTAS else a['puerto'])


def guardar_ajustes(cambios):
    propios = {}
    if os.path.exists(AJUSTES):
        with open(AJUSTES, encoding='utf-8') as f:
            propios = json.load(f)
    propios.update(cambios)
    with open(AJUSTES + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(propios, f, ensure_ascii=False, indent=1)
    os.replace(AJUSTES + '.tmp', AJUSTES)


def quitar_ajustes(claves):
    """Vuelve a los valores por defecto: borra esas claves de los ajustes del usuario."""
    if not os.path.exists(AJUSTES):
        return
    with open(AJUSTES, encoding='utf-8') as f:
        propios = json.load(f)
    for k in claves:
        propios.pop(k, None)
    with open(AJUSTES + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(propios, f, ensure_ascii=False, indent=1)
    os.replace(AJUSTES + '.tmp', AJUSTES)


def ruta_garmin():
    return os.path.expanduser(ajustes()['dir_garmin'])


def ruta_garmin_db():
    return os.path.expanduser(ajustes()['garmin_db'])
