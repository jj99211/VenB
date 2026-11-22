"""Mantiene las bases de datos de garmindb (garmin.db, sleep.db, hrv.db, garmin_activities.db...) acordes con la
versión de garmindb instalada. Cada versión de garmindb puede cambiar el formato de sus bases (la 4.0.1 movió el
sueño y la VFC a bases propias y añadió columnas): una base de otra versión hace fallar las descargas a medias.

Se anota en <config>/bd_garmindb.json con qué versión de garmindb se crearon las bases. Si la instalada es otra (o
no hay anotación, o una descarga avisó de que hay que rehacerlas), las bases se rehacen desde los ficheros ya
descargados (HealthData/FitFiles, Sleep, RHR...), sin pedir nada a Garmin Connect. Las bases anteriores se guardan
en HealthData/DBs_copia (solo la última copia) y, si algo falla, se restauran.

Se ejecuta con el Python de garmindb. Uso:
  python garmin_bd.py <carpeta de configuración>                 comprueba y rehace si hace falta (instaladores)
  python garmin_bd.py <carpeta de configuración> -- <opciones>   lo mismo y después garmindb_cli.py con esas opciones
  python garmin_bd.py <carpeta de configuración> --marcar-rehacer   la próxima comprobación rehará las bases"""
import glob
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from importlib.metadata import version

MARCA = 'bd_garmindb.json'
# Avisos de garmindb que indican bases de otro formato (no son fallos de inicio de sesión)
FORMATO_ANTIGUO = r'version mismatch|Please rebuild|has no column named|no such column|no such table'


def version_garmindb():
    return version('garmindb')


def _marca(config):
    try:
        with open(os.path.join(config, MARCA), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _guardar_marca(config, datos):
    ruta = os.path.join(config, MARCA)
    with open(ruta + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    os.replace(ruta + '.tmp', ruta)


def marcar_rehacer(config):
    m = _marca(config)
    m['rehacer'] = True
    _guardar_marca(config, m)


def _dir_bases(config):
    from garmindb import GarminConnectConfigManager
    return GarminConnectConfigManager(config).get_db_dir()


def hace_falta(config):
    """(rehacer, motivo). Sin bases todavía, no hace falta (las crea la primera descarga)."""
    bases = glob.glob(os.path.join(_dir_bases(config), '*.db'))
    actual = version_garmindb()
    m = _marca(config)
    if not bases:
        return False, ''
    if m.get('rehacer'):
        return True, 'una descarga avisó de que las bases tienen otro formato'
    if not m.get('garmindb'):
        return True, f'no consta con qué versión de garmindb se crearon (instalada: {actual})'
    if m['garmindb'] != actual:
        return True, f"se crearon con garmindb {m['garmindb']} y ahora está instalada la {actual}"
    return False, ''


def rehacer(config, py=sys.executable):
    """Rehace todas las bases desde los ficheros descargados. Devuelve True si ha ido bien."""
    dbs = _dir_bases(config)
    copia = os.path.join(os.path.dirname(dbs.rstrip(os.sep)), 'DBs_copia')
    shutil.rmtree(copia, ignore_errors=True)
    os.makedirs(copia)
    for f in glob.glob(os.path.join(dbs, '*.db')) + glob.glob(os.path.join(dbs, '*.db-journal')):
        shutil.move(f, copia)
    cli = os.path.join(os.path.dirname(py), 'garmindb_cli.py')
    log = os.path.join(config, 'rehacer_bases.log')
    with open(log, 'w', encoding='utf-8') as f:
        r = subprocess.run([py, cli, '-f', config, '--simple-output', '--rebuild_db'], stdout=f, stderr=subprocess.STDOUT,
                           cwd=config, stdin=subprocess.DEVNULL, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    with open(log, encoding='utf-8', errors='replace') as f:
        texto = f.read()
    import re
    if r.returncode != 0 or 'Traceback' in texto or re.search(FORMATO_ANTIGUO, texto):
        # se vuelve a lo anterior: mejor bases antiguas que ninguna
        for f in glob.glob(os.path.join(dbs, '*.db')) + glob.glob(os.path.join(dbs, '*.db-journal')):
            os.remove(f)
        for f in os.listdir(copia):
            shutil.move(os.path.join(copia, f), dbs)
        print(f'No se han podido rehacer las bases de Garmin (detalles en {log}); se conservan las anteriores.')
        return False
    _guardar_marca(config, {'garmindb': version_garmindb(), 'fecha': datetime.now().isoformat(timespec='seconds')})
    print(f'Bases de Garmin rehechas para garmindb {version_garmindb()} (copia de las anteriores en {copia}).')
    return True


def asegurar(config, py=sys.executable):
    """Comprueba y, si hace falta, rehace. Sin bases, anota la versión para las que se crearán."""
    falta, motivo = hace_falta(config)
    if not falta:
        if not glob.glob(os.path.join(_dir_bases(config), '*.db')) or not _marca(config).get('garmindb'):
            _guardar_marca(config, {'garmindb': version_garmindb(), 'fecha': datetime.now().isoformat(timespec='seconds')})
        return True
    print(f'Hay que rehacer las bases de datos de Garmin: {motivo}.')
    print('Se rehacen con los ficheros ya descargados, sin pedir nada a Garmin Connect. Puede tardar entre 10 y 30 minutos...', flush=True)
    return rehacer(config, py)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    config = sys.argv[1]
    if sys.argv[2:3] == ['--marcar-rehacer']:
        marcar_rehacer(config)
        return 0
    ok = asegurar(config)
    if '--' not in sys.argv:
        return 0 if ok else 1
    if not ok:
        return 1
    opciones = sys.argv[sys.argv.index('--') + 1:]
    sys.stdout.flush()
    cli = os.path.join(os.path.dirname(sys.executable), 'garmindb_cli.py')
    return subprocess.run([sys.executable, cli, '-f', config] + opciones, cwd=config, stdin=subprocess.DEVNULL).returncode


if __name__ == '__main__':
    sys.exit(main())
