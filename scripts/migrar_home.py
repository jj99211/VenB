"""Reúne en ~/.venb lo que VenB tenía repartido por la carpeta personal (hasta la versión 2.10):
  ~/.GarminDb        -> ~/.venb/garmin       configuración y sesión de garmindb
  ~/HealthData       -> ~/.venb/HealthData   datos descargados de Garmin
  ~/garmindb.log     -> ~/.venb/garmin       registro de garmindb
Los entornos de Python (~/.venvs/venb y ~/.venvs/garmindb) los crea de nuevo el instalador en ~/.venb/python y
después borra los antiguos. Lo ejecuta el instalador; se puede repetir sin riesgo: lo ya movido no se toca."""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rutas  # noqa: E402

CASA = os.path.expanduser('~')
CONFIG = os.path.join(rutas.GARMIN_CONFIG, 'GarminConnectConfig.json')


def _mover(origen, destino):
    """Mueve si el origen existe y el destino no. Devuelve True si ha movido algo."""
    if not os.path.exists(origen) or os.path.exists(destino):
        return False
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    shutil.move(origen, destino)
    print(f'  {origen} -> {destino}')
    return True


def garmindb():
    viejo = os.path.join(CASA, '.GarminDb')
    if os.path.isdir(viejo):
        os.makedirs(rutas.GARMIN_CONFIG, mode=0o700, exist_ok=True)
        for f in os.listdir(viejo):
            _mover(os.path.join(viejo, f), os.path.join(rutas.GARMIN_CONFIG, f))
        if not os.listdir(viejo):
            os.rmdir(viejo)
    _mover(os.path.join(CASA, 'garmindb.log'), os.path.join(rutas.GARMIN_CONFIG, 'garmindb.log'))


def healthdata():
    """Solo si garmindb usaba su carpeta por defecto: una ruta elegida por el usuario se respeta."""
    if not os.path.exists(CONFIG):
        return
    with open(CONFIG, encoding='utf-8') as f:
        config = json.load(f)
    d = config.setdefault('directories', {})
    if not d.get('relative_to_home', True) or d.get('base_dir', 'HealthData') != 'HealthData':
        return
    _mover(os.path.join(CASA, 'HealthData'), os.path.join(rutas.INTERNO, 'HealthData'))
    d.update(relative_to_home=True, base_dir=rutas.BASE_HEALTHDATA)
    with open(CONFIG + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
    try:
        os.chmod(CONFIG + '.tmp', 0o600)
    except OSError:
        pass
    os.replace(CONFIG + '.tmp', CONFIG)
    print(f'  garmindb guarda ahora sus datos en ~/{rutas.BASE_HEALTHDATA}')


if __name__ == '__main__':
    os.makedirs(rutas.INTERNO, mode=0o700, exist_ok=True)
    garmindb()
    healthdata()
