"""Extrae de la exportación de Garmin el historial de actividades y de peso.
Uso: python venb/importar_historico.py exportacion_garmin.zip
Solo guarda esas dos tablas en VenB-datos/datos/; no copia el resto de datos personales del zip.
También se puede importar desde Ajustes, que antes guarda una copia del estado actual (ver copia.py)."""
import csv, json, os, sys, zipfile
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, '..', 'scripts'))
import rutas  # noqa: E402


def _escribir(nombre, cabecera, filas):
    ruta = os.path.join(rutas.DATOS, nombre)
    with open(ruta + '.tmp', 'w', newline='', encoding='utf-8') as f:
        e = csv.writer(f)
        e.writerow(cabecera)
        e.writerows(filas)
    os.replace(ruta + '.tmp', ruta)


def importar(ruta_zip):
    """Sustituye historico_actividades.csv y peso_historico.csv. Devuelve cuántas filas se han guardado."""
    actividades, pesos = {}, []
    with zipfile.ZipFile(ruta_zip) as z:
        for n in z.namelist():
            if n.endswith('summarizedActivities.json'):
                for bloque in json.load(z.open(n)):
                    for a in bloque.get('summarizedActivitiesExport', []):
                        if a.get('startTimeLocal'):
                            actividades[a['activityId']] = a
            elif n.endswith('userBioMetrics.json'):
                for x in json.load(z.open(n)):
                    w = x.get('weight')
                    if isinstance(w, dict) and w.get('weight'):
                        pesos.append((x['metaData']['calendarDate'][:10], round(w['weight'] / 1000, 1)))
    filas = []
    for a in actividades.values():
        fecha = datetime.fromtimestamp(a['startTimeLocal'] / 1000, timezone.utc)
        if fecha.year < 2000:  # el reloj sin fecha registra 1990
            continue
        mov = a.get('movingDuration') or a.get('duration') or 0
        tot = a.get('elapsedDuration') or a.get('duration') or mov
        filas.append([a['activityId'], fecha.strftime('%Y-%m-%d %H:%M:%S'), a.get('activityType'), a.get('name') or '',
                      round((a.get('distance') or 0) / 1e5, 2), round(mov / 3.6e6, 4), round(tot / 3.6e6, 4),
                      round((a.get('elevationGain') or 0) / 100)])
    if actividades:
        _escribir('historico_actividades.csv', ['id', 'fecha', 'tipo', 'titulo', 'km', 'h', 'h_total', 'desnivel'], filas)
    if pesos:
        _escribir('peso_historico.csv', ['fecha', 'kg'], sorted(set(pesos)))
    return {'actividades': len(filas), 'pesos': len(set(pesos))}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('Uso: python venb/importar_historico.py exportacion_garmin.zip')
    r = importar(sys.argv[1])
    print(f'{r["actividades"]} actividades y {r["pesos"]} pesos importados')
