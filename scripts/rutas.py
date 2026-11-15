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


# ---------- Temporada ----------
# Una temporada lleva el año nominal: si empieza entre septiembre y diciembre, esos meses son del año siguiente
# (noviembre de 2026 abre la temporada 2027); si empieza entre febrero y abril, los meses anteriores son del año
# anterior (con inicio en abril, marzo de 2027 cierra la temporada 2026). En enero coincide con el año natural.
# Todas las estadísticas anuales se agrupan con estas funciones; nada se guarda agrupado, así que cambiar el mes
# en Ajustes recalcula todo el historial.
MESES_TEMPORADA = (9, 10, 11, 12, 1, 2, 3, 4)
_MESES_TXT = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']


def mes_inicio(a=None):
    """Mes de inicio de la temporada (septiembre a abril). Un valor antiguo de mayo a agosto pasa al más cercano."""
    try:
        m = int((a or ajustes()).get('mes_inicio_temporada', 11))
    except (TypeError, ValueError):
        m = 11
    if m in MESES_TEMPORADA:
        return m
    return 4 if 5 <= m <= 6 else 9 if 7 <= m <= 8 else 11


def temporada(anio, mes, inicio=None):
    """Temporada (año nominal) a la que pertenece un mes de un año natural."""
    i = inicio or mes_inicio()
    if i >= 9:
        return anio + 1 if mes >= i else anio
    return anio - 1 if mes < i else anio


def temporada_fecha(f, inicio=None):
    """Temporada de una fecha (date, datetime, Timestamp o texto AAAA-MM-DD…)."""
    if isinstance(f, str):
        return temporada(int(f[:4]), int(f[5:7]), inicio)
    return temporada(f.year, f.month, inicio)


def temporadas_serie(fechas, inicio=None):
    """Temporada de cada fecha de una serie de pandas (datetime)."""
    i = inicio or mes_inicio()
    a, m = fechas.dt.year, fechas.dt.month
    if i >= 9:
        return (a + (m >= i).astype(int)).astype('Int64')
    return (a - (m < i).astype(int)).astype('Int64')


def inicio_temporada(t, inicio=None):
    """(año, mes) del primer mes de la temporada t."""
    i = inicio or mes_inicio()
    return (t - 1, i) if i >= 9 else (t, i)


def meses_temporada(inicio=None):
    """Los doce meses (1-12) en el orden de la temporada."""
    i = inicio or mes_inicio()
    return [(i - 1 + k) % 12 + 1 for k in range(12)]


def natural(t, mes, inicio=None):
    """Año natural de un mes de la temporada t."""
    a, i = inicio_temporada(t, inicio)
    return a if mes >= i else a + 1


def descripcion_temporada(t=None, inicio=None):
    """«De noviembre a octubre.» o, con t, «De noviembre de 2026 a octubre de 2027»."""
    i = inicio or mes_inicio()
    fin = (i - 2) % 12 + 1
    if i == 1:
        return f'Año natural {t}' if t else 'Por año natural.'
    if t is None:
        return f'De {_MESES_TXT[i - 1]} a {_MESES_TXT[fin - 1]}.'
    a, _ = inicio_temporada(t, i)
    return f'De {_MESES_TXT[i - 1]} de {a} a {_MESES_TXT[fin - 1]} de {natural(t, fin, i)}'
