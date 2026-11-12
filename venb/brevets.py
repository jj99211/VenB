"""Homologaciones de brevets de VenB. Se guarda en VenB-datos/datos/brevets.csv. También se puede anotar desde la terminal:
  python venb/brevets.py nuevo --fecha DD/MM/AAAA --tipo BRM --nombre "Mi brevet" --distancia 200 --tiempo 12:30 \
      --homologacion 123456 --organizador "Club A" --inscripcion "Club B" [--r5000] [--r10000] [--actividad ID_GARMIN]
VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0."""
import argparse
import csv
import json
import math
import os
import re
import sys
import uuid
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import rutas  # noqa: E402

RUTA = os.path.join(rutas.DATOS, 'brevets.csv')
CAMPOS = ['id', 'anio', 'fecha', 'tipo', 'nombre', 'distancia', 'homologacion', 'organizador', 'inscripcion', 'horas', 'r5000', 'r10000', 'actividad']


def todos():
    if not os.path.exists(RUTA):
        return []
    with open(RUTA, newline='', encoding='utf-8') as f:
        filas = list(csv.DictReader(f))
    for b in filas:
        b['distancia'] = float(b['distancia'] or 0)
        b['horas'] = float(b['horas']) if b['horas'] else None
        b['anio'] = int(b['anio'])
        for c in ('r5000', 'r10000', 'actividad'):  # columnas añadidas después: faltan en ficheros antiguos
            b[c] = b.get(c) or ''
    return sorted(filas, key=lambda b: (b['anio'], b['fecha']), reverse=True)


def guardar(filas):
    os.makedirs(rutas.DATOS, exist_ok=True)
    tmp = RUTA + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        e = csv.DictWriter(f, CAMPOS, restval='', extrasaction='ignore')
        e.writeheader()
        e.writerows(filas)
    os.replace(tmp, RUTA)


def leer_tiempo(txt):
    """Acepta H:MM (87:30) o solo horas. Devuelve horas, o None si va vacío."""
    txt = (txt or '').strip()
    if not txt:
        return None
    h, _, m = txt.partition(':')
    horas, minutos = int(h), int(m or 0)
    if horas < 0 or not 0 <= minutos < 60:
        raise ValueError
    return round(horas + minutos / 60, 4)


def formato_tiempo(h):
    if h is None:
        return ''
    minutos = round(h * 60)
    return f'{minutos // 60}:{minutos % 60:02d}'


def anotar(datos, bid=None):
    """Crea un brevet o, con bid, modifica ese. El año sale de la fecha."""
    filas = todos()
    fila = {**datos, 'anio': int(datos['fecha'][:4])}
    if bid:
        if not any(b['id'] == bid for b in filas):
            raise KeyError(bid)
        filas = [{**fila, 'id': bid} if b['id'] == bid else b for b in filas]
    else:
        filas.append({**fila, 'id': uuid.uuid4().hex})
    guardar(filas)


def borrar(bid):
    guardar([b for b in todos() if b['id'] != bid])


# Distancias homologables de brevets, superbrevets y flechas (km): para proponer la de una actividad
DISTANCIAS = (200, 300, 400, 600, 1000, 1200, 1400, 1500, 2000)


def distancia_nominal(km):
    """La mayor distancia homologable que no supera la recorrida en más de un 5 % (190 km -> 200; 213 -> 200; 1249 -> 1200)."""
    candidatas = [d for d in DISTANCIAS if d <= km * 1.05]
    return max(candidatas) if candidatas else round(km)


def _tramos(fs):
    """Días que ocupa cada prueba registrada: de la víspera al día siguiente de su final (12 km/h sin tiempo anotado)."""
    tramos = []
    for b in fs:
        ini = datetime.fromisoformat(b['fecha']).date().toordinal()
        tramos.append((ini - 1, ini + math.ceil((b['horas'] or b['distancia'] / 12) / 24) + 1))
    return tramos


def registradas(hist, km_min):
    """Ids de las salidas en bici de al menos km_min que ya corresponden a una prueba: enlazadas o deducidas por
    fecha y distancia (como en el historial de Brevets) o dentro de los días de una prueba (etapas)."""
    if hist is None or not len(hist):
        return set()
    fs = todos()
    ids = set(actividades(fs, hist).values())
    tramos = _tramos(fs)
    for a in hist[hist.bici & (hist.km >= km_min)].itertuples():
        ini, fin = a.fecha.date().toordinal(), a.fin.date().toordinal()
        if any(d <= fin and ini <= h for d, h in tramos):
            ids.add(str(a.id))
    return ids


def duplicado(datos, bid=None):
    """El brevet ya registrado con el que chocaría este (otro distinto de bid): el que tiene enlazada la misma actividad
    o uno de la misma fecha y distancia. None si no hay."""
    for b in todos():
        if b['id'] == bid:
            continue
        if datos.get('actividad') and b['actividad'] == datos['actividad']:
            return b
        if b['fecha'] == datos['fecha'] and abs(b['distancia'] - float(datos['distancia'])) < 1:
            return b
    return None


def brevet_de_actividad(aid, hist):
    """El brevet registrado al que corresponde una actividad (enlazada, deducida o etapa dentro de sus días), o None."""
    fs = todos()
    for bid, a in actividades(fs, hist).items():
        if a == str(aid):
            return next(b for b in fs if b['id'] == bid)
    fila = hist[hist.id.astype(str) == str(aid)] if hist is not None and len(hist) else None
    if fila is None or not len(fila):
        return None
    ini, fin = fila.iloc[0].fecha.date().toordinal(), fila.iloc[0].fin.date().toordinal()
    for b, (d, h) in zip(fs, _tramos(fs)):
        if d <= fin and ini <= h:
            return b
    return None


NO_PRUEBAS = os.path.join(rutas.DATOS, 'no_pruebas.json')
AVISOS_CERRADOS = os.path.join(rutas.DATOS, 'avisos_cerrados.json')


def _leer_json(ruta, defecto):
    try:
        with open(ruta, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def _escribir_json(ruta, valor):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(valor, f, ensure_ascii=False, indent=1)
    os.replace(ruta + '.tmp', ruta)


def no_pruebas():
    """Ids de las salidas marcadas «No es prueba» (VenB-datos/datos/no_pruebas.json). También cuentan las que se
    cerraron con la × en el aviso de Inicio («Si fue una salida sin más, ciérralo con la ×»)."""
    ids = {str(x) for x in _leer_json(NO_PRUEBAS, [])}
    return ids | {c[7:] for c in _leer_json(AVISOS_CERRADOS, []) if c.startswith('prueba:')}


def marcar_no_prueba(ids):
    _escribir_json(NO_PRUEBAS, sorted({str(x) for x in _leer_json(NO_PRUEBAS, [])} | {str(i) for i in ids}))


def recuperar(aid):
    """Quita la marca «No es prueba» (y el aviso cerrado de Inicio) de una salida: vuelve a «por clasificar»."""
    aid = str(aid)
    _escribir_json(NO_PRUEBAS, sorted(str(x) for x in _leer_json(NO_PRUEBAS, []) if str(x) != aid))
    cerrados = _leer_json(AVISOS_CERRADOS, None)
    if cerrados is not None and f'prueba:{aid}' in cerrados:
        _escribir_json(AVISOS_CERRADOS, [c for c in cerrados if c != f'prueba:{aid}'])


def sin_registrar(hist, km_min, dias=None, hoy=None, marcadas=False):
    """Salidas en bici de al menos km_min (de los últimos `dias`; None, todas) que no corresponden a ninguna prueba
    registrada: ni enlazada por su actividad ni dentro de los días que dura una prueba (de la víspera al día siguiente
    de su final) ni marcada «No es prueba» (con marcadas=True, solo las marcadas). Sin tiempo anotado, la duración se
    estima a 12 km/h, así que las etapas de una prueba larga también cuentan."""
    if hist is None or not len(hist):
        return []
    fs = todos()
    enlazadas = {b['actividad'] for b in fs if b['actividad']}
    tramos = _tramos(fs)
    desde = hoy.toordinal() - dias if dias is not None else 0
    no = no_pruebas()
    salida = []
    for a in hist[hist.bici & (hist.km >= km_min)].sort_values('fecha', ascending=False).itertuples():
        ini, fin = a.fecha.date(), a.fin.date()
        if ini.toordinal() < desde or str(a.id) in enlazadas or (str(a.id) in no) != marcadas:
            continue
        if any(desde_p <= fin.toordinal() and ini.toordinal() <= hasta_p for desde_p, hasta_p in tramos):
            continue
        salida.append(a)
    return salida


URL_GARMIN = 'https://connect.garmin.com/modern/activity/{}'


def actividades(fs, hist):
    """{id del brevet: id de su actividad de Garmin}. Manda la enlazada; si no hay, se busca una salida en bici en exterior
    del mismo día (o del anterior o el siguiente, por fechas aproximadas) con al menos la mitad de la distancia, la más parecida.
    Si la prueba se grabó por etapas, la etapa más larga del día de salida (con al menos un cuarto de la distancia)."""
    salida = {b['id']: b['actividad'] for b in fs if b['actividad']}
    if hist is None or not len(hist):
        return salida
    h = hist[hist.bici & ~hist.tipo.isin(['Ciclismo virtual', 'Ciclismo en sala'])]
    dias = h.fecha.dt.date
    for b in fs:
        if b['id'] in salida:
            continue
        f = datetime.fromisoformat(b['fecha']).date()
        mejor = None
        for desfase in (0, 1, -1):
            c = h[(dias == date.fromordinal(f.toordinal() + desfase)) & (h.km >= b['distancia'] * 0.5)]
            if len(c):
                mejor = c.loc[(c.km - b['distancia']).abs().idxmin()]
                break
        if mejor is None:
            c = h[(dias == f) & (h.km >= b['distancia'] * 0.25)]
            if len(c):
                mejor = c.loc[c.km.idxmax()]
        if mejor is not None:
            salida[b['id']] = str(mejor.id)
    return salida


# Etapas de una prueba de varios días (o grabada en varias actividades): «PBP2019_Etapa01», «BRM600 Demanda_SinGPS»
ETAPA = re.compile(r'_(Etapa\d+|SinGPS)$')


def pruebas(fs=None):
    """Brevets agrupados por prueba: las filas «<nombre>_EtapaXX» y «<nombre>_SinGPS» del mismo tipo y separadas menos
    de 10 días forman una sola prueba, con la suma de sus km (los reales) y la distancia homologable que les corresponde.
    Cada prueba: {'nombre', 'tipo', 'fecha', 'anio', 'distancia', 'nominal', 'horas' (solo si es de una fila),
    'r5000', 'r10000', 'homologacion', 'etapas'}."""
    fs = sorted(todos() if fs is None else fs, key=lambda b: b['fecha'])
    grupos, abiertos = [], {}
    for b in fs:
        base = ETAPA.sub('', b['nombre'] or '')
        clave = (base, b['tipo']) if base != (b['nombre'] or '') else None
        g = abiertos.get(clave) if clave else None
        if g and datetime.fromisoformat(b['fecha']).toordinal() - datetime.fromisoformat(g['fecha']).toordinal() < 10:
            g['filas'].append(b)
            continue
        g = {'nombre': base if clave else b['nombre'], 'tipo': b['tipo'], 'fecha': b['fecha'], 'anio': b['anio'], 'filas': [b]}
        grupos.append(g)
        if clave:
            abiertos[clave] = g
    for g in grupos:
        fl = g.pop('filas')
        g['distancia'] = round(sum(b['distancia'] for b in fl), 1)
        nom = distancia_nominal(g['distancia'])   # una prueba incompleta (LEL2025, 926 km) conserva sus km reales
        g['nominal'] = fl[0]['distancia'] if len(fl) == 1 else (nom if nom >= g['distancia'] * 0.9 else round(g['distancia']))
        g['horas'] = fl[0]['horas'] if len(fl) == 1 else None    # la suma de etapas no es el tiempo de la prueba
        for c in ('r5000', 'r10000', 'homologacion'):
            g[c] = next((b[c] for b in fl if b[c]), '')
        g['etapas'] = len(fl)
        g['actividades'] = [b['actividad'] for b in fl]
        g['sin_gps'] = any(b['actividad'] == 'manual' or (b['nombre'] or '').endswith('_SinGPS') for b in fl)
    return grupos


def categoria(p):
    """(orden, texto) de la categoría en la que compite una prueba por el mejor tiempo: cada distancia de BRM, las SR,
    cada superbrevet por sus siglas (PBP, LEL, MGM…), las Flechas y, el resto, por tipo y distancia."""
    d = p['nominal']
    if p['tipo'] == 'BRM':
        return (0, d, ''), f'BRM {d:g} km'
    if p['tipo'] == 'SR':
        return (1, 0, ''), 'SR'
    if p['tipo'] == 'SB':
        m = re.match(r'[A-Za-zÀ-ÿ]+', p['nombre'] or '')
        sigla = m.group().upper() if m else 'SB'
        return (2, 0, sigla), f'SB {sigla}' if sigla != 'SB' else 'SB'
    if p['tipo'] == 'Flecha':
        return (3, 0, ''), 'Flecha'
    return (4, d, p['tipo']), f'{p["tipo"]} {d:g} km'


def tiempo_total(p, hist):
    """Horas de una prueba: la de su fila o, si está por etapas, de la salida de la primera actividad al final de la última
    (con paradas y noches, como un tiempo oficial). None si falta algún dato, tiene km sin grabar o quedó incompleta
    (no llega a una distancia homologable, como la LEL2025 suspendida en el km 926)."""
    if p['etapas'] == 1:
        return p['horas']
    if p['sin_gps'] or p['nominal'] not in DISTANCIAS or hist is None or not len(hist):   # km sin grabar o incompleta
        return None
    sel = hist[hist.id.astype(str).isin([str(a) for a in p['actividades']])]
    if len(sel) != p['etapas'] or sel.fin.isna().any():
        return None
    return round((sel.fin.max() - sel.fecha.min()).total_seconds() / 3600, 4)


def estadisticas(hist=None):
    """Cifras, kilómetros por año y tramo, y mejor tiempo por categoría, contando cada prueba una vez aunque esté
    registrada por etapas (los km son siempre los de las filas, sin duplicar). Con hist (historial de actividades),
    las pruebas por etapas compiten con su tiempo total (ver tiempo_total)."""
    fs = todos()
    if not fs:
        return None
    ps = pruebas(fs)
    anios = list(range(min(b['anio'] for b in fs), max(b['anio'] for b in fs) + 1))
    series = [{'n': n, 'v': [sum(p['distancia'] for p in ps if p['anio'] == a and lo <= p['distancia'] < hi) for a in anios]} for n, lo, hi in rutas.ajustes()['tramos_brevet']]
    cats = {}
    for p in ps:
        orden, texto = categoria(p)
        c = cats.setdefault(orden, {'categoria': texto, 'n': 0, 'mejor': None})
        c['n'] += 1
        h = tiempo_total(p, hist)
        if h and (c['mejor'] is None or h < c['mejor'][0]):
            c['mejor'] = (h, p)
    mejores = [{'categoria': c['categoria'], 'n': c['n'], 'horas': c['mejor'][0], 'nombre': c['mejor'][1]['nombre'], 'fecha': c['mejor'][1]['fecha'],
                'km': c['mejor'][1]['distancia'], 'etapas': c['mejor'][1]['etapas']} for o, c in sorted(cats.items()) if c['mejor']]
    return {'n': len(ps), 'km': sum(b['distancia'] for b in fs), 'r5000': sum(1 for p in ps if p['r5000']), 'r10000': sum(1 for p in ps if p['r10000']),
            'pendientes': sum(1 for p in ps if not p['homologacion']), 'anios': anios, 'series': series, 'mejores': mejores}


def _cli():
    p = argparse.ArgumentParser(description='Brevets de VenB')
    s = p.add_subparsers(dest='orden', required=True)
    n = s.add_parser('nuevo')
    n.add_argument('--fecha', required=True, help='DD/MM/AAAA')
    n.add_argument('--tipo', choices=rutas.ajustes()['tipos_brevet'], default=rutas.ajustes()['tipos_brevet'][0])
    n.add_argument('--nombre', default='')
    n.add_argument('--distancia', type=float, required=True)
    n.add_argument('--tiempo', default='', help='H:MM')
    n.add_argument('--homologacion', default='')
    n.add_argument('--organizador', default='')
    n.add_argument('--inscripcion', default='')
    n.add_argument('--r5000', action='store_true')
    n.add_argument('--r10000', action='store_true')
    n.add_argument('--actividad', default='', help='id de la actividad de Garmin')
    a = p.parse_args()
    anotar({'fecha': datetime.strptime(a.fecha, '%d/%m/%Y').date().isoformat(), 'tipo': a.tipo, 'nombre': a.nombre, 'distancia': a.distancia, 'homologacion': a.homologacion,
            'organizador': a.organizador, 'inscripcion': a.inscripcion, 'horas': leer_tiempo(a.tiempo), 'r5000': '1' if a.r5000 else '',
            'r10000': '1' if a.r10000 else '', 'actividad': a.actividad})
    print('Anotado.')


if __name__ == '__main__':
    _cli()
