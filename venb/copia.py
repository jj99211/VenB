"""Copia de seguridad de VenB y restauración, también de la exportación de cuenta de Garmin.
Uso: python venb/copia.py exportar [CARPETA]   crea VenB-copia-AAAA-MM-DD_HHMM.zip (por defecto, en la carpeta actual)
     python venb/copia.py importar ZIP         restaura una copia de VenB o importa una exportación de Garmin
     python venb/copia.py comprobar ZIP        verifica una copia sin tocar nada

Una copia contiene VenB-datos entera (salvo cachés y las copias automáticas) y, de los datos de garmindb, lo que VenB
lee: los resúmenes JSON de las actividades y la base garmin.db (sueño, VFC, FC en reposo y peso). Los FIT originales
no entran: VenB no los usa y garmindb puede volver a descargarlos.
No entra nada secreto: ni la contraseña de Garmin, que está en ~/.venb, ni la dirección del calendario (config/calendario_url.txt).
Cada fichero lleva su suma SHA-256 en copia_venb.json; antes de restaurar se comprueban todas, y antes de sobrescribir
nada se guarda el estado actual en VenB-datos/copias/ (las 5 últimas). Los ficheros de VenB-datos se sustituyen; los de garmindb solo
se añaden si faltan, para no pisar descargas más recientes."""
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'scripts'))
import rutas  # noqa: E402
import importar_historico  # noqa: E402

MANIFIESTO = 'copia_venb.json'
FORMATO = 1
GUARDAR = 5  # copias automáticas que se conservan
COPIAS = os.path.join(rutas.PERSISTE, 'copias')
EXCLUIR = ('copias/', 'actividades/pendientes/', 'datos/calendario_cache.ics', 'datos/calendario_propio_cache.ics', 'datos/cortes_cache.json', 'datos/sensores_cache.json', 'config/calendario_url.txt')
P_DATOS, P_ACT, P_DB = 'VenB-datos/', 'garmin/actividades/', 'garmin/garmin.db'


class ErrorCopia(Exception):
    pass


def _sha(datos):
    return hashlib.sha256(datos).hexdigest()


def _db_consistente(ruta):
    """Copia de la base con la API de SQLite: es coherente aunque garmindb la esté escribiendo."""
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    origen = sqlite3.connect(f'file:{ruta}?mode=ro', uri=True)
    destino = sqlite3.connect(tmp.name)
    try:
        origen.backup(destino)
    finally:
        destino.close()
        origen.close()
    with open(tmp.name, 'rb') as f:
        datos = f.read()
    os.unlink(tmp.name)
    return datos


def _ficheros():
    """(nombre en el ZIP, ruta local o función que da los bytes)."""
    for d, subdirs, fs in os.walk(rutas.PERSISTE):
        subdirs[:] = [s for s in subdirs if s != '__pycache__']
        for f in fs:
            ruta = os.path.join(d, f)
            rel = os.path.relpath(ruta, rutas.PERSISTE).replace(os.sep, '/')
            if not rel.startswith(EXCLUIR) and rel not in EXCLUIR and not f.endswith(('.tmp', '.pyc')):
                yield P_DATOS + rel, ruta
    act = rutas.ruta_garmin()
    if os.path.isdir(act):
        for f in sorted(os.listdir(act)):
            if f.endswith('.json'):
                yield P_ACT + f, os.path.join(act, f)
    db = rutas.ruta_garmin_db()
    if os.path.exists(db):
        yield P_DB, lambda: _db_consistente(db)


def _escribir_copia(destino):
    lista = {}
    tmp = destino + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for nombre, origen in _ficheros():
            if callable(origen):
                datos = origen()
            else:
                with open(origen, 'rb') as f:
                    datos = f.read()
            z.writestr(nombre, datos)
            lista[nombre] = _sha(datos)
        z.writestr(MANIFIESTO, json.dumps({'formato': FORMATO, 'fecha': datetime.now().isoformat(timespec='seconds'),
                                           'version': _version(), 'ficheros': lista}, ensure_ascii=False, indent=1))
    comprobar(tmp)
    os.replace(tmp, destino)
    return destino


def _version():
    try:
        from version import VERSION
        return VERSION
    except Exception:
        return 'desconocida'


def exportar(carpeta='.'):
    """Crea la copia en CARPETA y la verifica. Devuelve su ruta."""
    os.makedirs(carpeta, exist_ok=True)
    return _escribir_copia(os.path.join(carpeta, f'VenB-copia-{datetime.now():%Y-%m-%d_%H%M}.zip'))


def _nombre_valido(n):
    partes = n.split('/')
    if n.startswith('/') or '\\' in n or ':' in n or any(p in ('', '.', '..') for p in partes):
        return False
    if n.startswith(P_DATOS):
        return len(partes) > 1
    if n.startswith(P_ACT):
        return len(partes) == 3 and n.endswith('.json')
    return n in (P_DB, MANIFIESTO)


def comprobar(ruta):
    """Verifica que el ZIP es una copia de VenB íntegra. Devuelve su manifiesto."""
    try:
        with zipfile.ZipFile(ruta) as z:
            if MANIFIESTO not in z.namelist():
                raise ErrorCopia('No es una copia de VenB.')
            m = json.loads(z.read(MANIFIESTO))
            if m.get('formato') != FORMATO:
                raise ErrorCopia('Esta copia es de un formato que esta versión de VenB no reconoce.')
            nombres = set(z.namelist()) - {MANIFIESTO}
            if nombres != set(m['ficheros']):
                raise ErrorCopia('La copia está incompleta: faltan o sobran ficheros respecto a su índice.')
            for n in nombres:
                if not _nombre_valido(n):
                    raise ErrorCopia(f'La copia contiene una ruta no válida: {n}')
                if _sha(z.read(n)) != m['ficheros'][n]:
                    raise ErrorCopia(f'La copia está dañada: {n} no coincide con su suma de control.')
    except (zipfile.BadZipFile, ValueError, KeyError, TypeError) as e:
        raise ErrorCopia(f'El fichero no es un ZIP válido o está dañado ({e}).')
    return m


def tipo(ruta):
    """'copia', 'garmin' o None."""
    try:
        with zipfile.ZipFile(ruta) as z:
            nombres = z.namelist()
    except zipfile.BadZipFile:
        return None
    if MANIFIESTO in nombres:
        return 'copia'
    if any(n.endswith(('summarizedActivities.json', 'userBioMetrics.json')) for n in nombres):
        return 'garmin'
    return None


def _guardar(ruta, datos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta + '.tmp', 'wb') as f:
        f.write(datos)
    os.replace(ruta + '.tmp', ruta)


def copia_previa():
    """Estado actual, por si hay que deshacer una restauración o una importación."""
    os.makedirs(COPIAS, exist_ok=True)
    ruta = _escribir_copia(os.path.join(COPIAS, f'antes-de-importar-{datetime.now():%Y-%m-%d_%H%M%S}.zip'))
    previas = sorted(f for f in os.listdir(COPIAS) if f.startswith('antes-de-importar-') and f.endswith('.zip'))
    for f in previas[:-GUARDAR]:
        os.remove(os.path.join(COPIAS, f))
    return ruta


def restaurar(ruta):
    m = comprobar(ruta)
    previa = copia_previa()
    n_datos = n_act = 0
    db = 'no incluida'
    with zipfile.ZipFile(ruta) as z:
        for n in sorted(m['ficheros']):
            if n.startswith(P_DATOS):
                _guardar(os.path.join(rutas.PERSISTE, *n[len(P_DATOS):].split('/')), z.read(n))
                n_datos += 1
            elif n.startswith(P_ACT):
                destino = os.path.join(rutas.ruta_garmin(), n[len(P_ACT):])
                if not os.path.exists(destino):
                    _guardar(destino, z.read(n))
                    n_act += 1
            elif n == P_DB:
                if os.path.exists(rutas.ruta_garmin_db()):
                    db = 'se conserva la actual'
                else:
                    _guardar(rutas.ruta_garmin_db(), z.read(n))
                    db = 'restaurada'
    return {'tipo': 'copia', 'fecha': m['fecha'], 'datos': n_datos, 'actividades': n_act, 'db': db, 'previa': previa}


def importar(ruta):
    """Restaura una copia de VenB o importa una exportación de cuenta de Garmin, según lo que sea el ZIP."""
    t = tipo(ruta)
    if t == 'copia':
        return restaurar(ruta)
    if t == 'garmin':
        previa = copia_previa()
        r = importar_historico.importar(ruta)
        return {'tipo': 'garmin', 'previa': previa, **r}
    raise ErrorCopia('El ZIP no es una copia de VenB ni una exportación de cuenta de Garmin.')


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('exportar', 'importar', 'comprobar'):
        sys.exit(__doc__)
    try:
        if sys.argv[1] == 'exportar':
            print(exportar(sys.argv[2] if len(sys.argv) > 2 else '.'))
        elif len(sys.argv) < 3:
            sys.exit(__doc__)
        elif sys.argv[1] == 'comprobar':
            m = comprobar(sys.argv[2])
            print(f'Copia íntegra del {m["fecha"]}, VenB {m["version"]}, {len(m["ficheros"])} ficheros.')
        else:
            print(json.dumps(importar(sys.argv[2]), ensure_ascii=False, indent=1))
    except ErrorCopia as e:
        sys.exit(str(e))


if __name__ == '__main__':
    main()
