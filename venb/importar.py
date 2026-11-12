"""Actividades de ficheros GPX, FIT o TCX subidos a mano, sin pasar por Garmin Connect.
Cada fichero original se guarda en VenB-datos/actividades/AAAA/ y su resumen en VenB-datos/datos/actividades_locales.csv,
que carga.py suma a las actividades de Garmin. La subida va en dos pasos: preparar() lee los ficheros y deja un lote
pendiente para revisar (tipo, título, bici, duplicados); confirmar() lo incorpora.
Identificadores: «L» + fecha y hora de inicio (L20261108093000), para no chocar con los de Garmin.
VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0."""
import csv
import gzip
import json
import math
import os
import re
import shutil
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import rutas  # noqa: E402

CARPETA = os.path.join(rutas.PERSISTE, 'actividades')
PENDIENTES = os.path.join(CARPETA, 'pendientes')
CSV = os.path.join(rutas.DATOS, 'actividades_locales.csv')
CAMPOS = ['id', 'fecha', 'tipo', 'titulo', 'km', 'h', 'h_total', 'desnivel', 'fc_media', 'fc_max',
          'potencia_media', 'potencia_max', 'np', 'p20', 'tss', 'calorias', 'fichero', 'importada']
EXTENSIONES = ('.gpx', '.fit', '.tcx')
# tipos que puede tener una actividad subida a mano: los mismos nombres que usa carga.py con Garmin
TIPOS = ['Ciclismo', 'Ciclismo en ruta', 'Ciclismo de montaña', 'Ciclismo en sala', 'Ciclismo virtual', 'Carrera', 'Caminar', 'Otros']
VEL_MIN = 0.6      # m/s: por debajo, el tiempo no cuenta como «en movimiento» ni la distancia entre posiciones (deriva del GPS parado)
UMBRAL_DESNIVEL = 3.0   # m: oscilaciones menores no suman desnivel
ES_ID = re.compile(r'L\d{14}(-\d+)?')


class ErrorFichero(Exception):
    pass


# ---------------------------------------------------------------- lectura de ficheros

def _local(t):
    """Hora UTC (aware o naive en UTC) a hora local del ordenador, sin zona."""
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone().replace(tzinfo=None)


def _hora_iso(texto):
    texto = texto.strip().replace('Z', '+00:00')
    texto = re.sub(r'\.(\d{1,6})\d*', r'.\1', texto)
    return datetime.fromisoformat(texto)


def _sin_ns(etiqueta):
    return etiqueta.rsplit('}', 1)[-1]


def _hijo(e, nombre):
    for x in e:
        if _sin_ns(x.tag) == nombre:
            return x
    return None


def _texto(e, nombre):
    x = _hijo(e, nombre) if e is not None else None
    return x.text.strip() if x is not None and x.text else None


def _num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _tipo(texto, sub=''):
    t = f'{texto or ""} {sub or ""}'.lower()
    if any(k in t for k in ('virtual', 'indoor', 'trainer', 'sala')):
        return 'Ciclismo virtual' if 'virtual' in t else 'Ciclismo en sala'
    if any(k in t for k in ('mountain', 'mtb', 'btt')):
        return 'Ciclismo de montaña'
    if 'road' in t:
        return 'Ciclismo en ruta'
    if any(k in t for k in ('cycl', 'bik', 'ride', 'gravel', 'ciclis')):
        return 'Ciclismo'
    if any(k in t for k in ('run', 'carrera')):
        return 'Carrera'
    if any(k in t for k in ('walk', 'hik', 'camin', 'sender')):
        return 'Caminar'
    return None


def leer_gpx(ruta):
    raiz = ET.parse(ruta).getroot()
    puntos, nombre, tipo = [], None, None
    for trk in raiz.iter():
        if _sin_ns(trk.tag) != 'trk':
            continue
        nombre, tipo = nombre or _texto(trk, 'name'), tipo or _texto(trk, 'type')
        for p in trk.iter():
            if _sin_ns(p.tag) != 'trkpt':
                continue
            t = _texto(p, 'time')
            if not t:
                continue
            fc = pot = None
            ext = _hijo(p, 'extensions')
            if ext is not None:
                for x in ext.iter():
                    n = _sin_ns(x.tag).lower()
                    if n == 'hr':
                        fc = _num(x.text)
                    elif n in ('power', 'watts'):
                        pot = _num(x.text)
            puntos.append({'t': _hora_iso(t), 'lat': _num(p.get('lat')), 'lon': _num(p.get('lon')),
                           'ele': _num(_texto(p, 'ele')), 'fc': fc, 'pot': pot})
    if not nombre:
        meta = _hijo(raiz, 'metadata')
        nombre = _texto(meta, 'name') if meta is not None else None
    return {'puntos': puntos, 'nombre': nombre, 'tipo': _tipo(tipo), 'sesion': {}}


def leer_tcx(ruta):
    raiz = ET.parse(ruta).getroot()
    puntos, tipo, sesion = [], None, {}
    for act in raiz.iter():
        if _sin_ns(act.tag) != 'Activity':
            continue
        tipo = tipo or _tipo(act.get('Sport'))
        for vuelta in act:
            if _sin_ns(vuelta.tag) != 'Lap':
                continue
            for k, c in (('calorias', 'Calories'),):
                v = _num(_texto(vuelta, c))
                if v:
                    sesion[k] = sesion.get(k, 0) + v
            for tp in vuelta.iter():
                if _sin_ns(tp.tag) != 'Trackpoint':
                    continue
                t = _texto(tp, 'Time')
                if not t:
                    continue
                pos = _hijo(tp, 'Position')
                fc = _hijo(tp, 'HeartRateBpm')
                pot = None
                for x in tp.iter():
                    if _sin_ns(x.tag) == 'Watts':
                        pot = _num(x.text)
                puntos.append({'t': _hora_iso(t), 'lat': _num(_texto(pos, 'LatitudeDegrees')) if pos is not None else None,
                               'lon': _num(_texto(pos, 'LongitudeDegrees')) if pos is not None else None,
                               'ele': _num(_texto(tp, 'AltitudeMeters')), 'dist': _num(_texto(tp, 'DistanceMeters')),
                               'fc': _num(_texto(fc, 'Value')) if fc is not None else None, 'pot': pot})
    return {'puntos': puntos, 'nombre': None, 'tipo': tipo, 'sesion': sesion}


def leer_fit(ruta):
    import fitparse
    try:
        f = fitparse.FitFile(ruta)
        f.parse()
    except Exception as e:
        raise ErrorFichero(f'No es un FIT válido ({e}).')
    semi = 180 / 2 ** 31
    puntos = []
    for m in f.get_messages('record'):
        v = m.get_values()
        if not v.get('timestamp'):
            continue
        lat, lon = v.get('position_lat'), v.get('position_long')
        puntos.append({'t': v['timestamp'], 'lat': lat * semi if lat is not None else None, 'lon': lon * semi if lon is not None else None,
                       'ele': _num(v.get('enhanced_altitude', v.get('altitude'))), 'dist': _num(v.get('distance')),
                       'fc': _num(v.get('heart_rate')), 'pot': _num(v.get('power'))})
    sesion, tipo = {}, None
    for m in f.get_messages('session'):
        v = m.get_values()
        tipo = _tipo(str(v.get('sport') or ''), str(v.get('sub_sport') or ''))
        sesion = {'inicio': v.get('start_time'), 'km': _num(v.get('total_distance')), 'h': _num(v.get('total_timer_time')),
                  'h_total': _num(v.get('total_elapsed_time')), 'desnivel': _num(v.get('total_ascent')),
                  'fc_media': _num(v.get('avg_heart_rate')), 'fc_max': _num(v.get('max_heart_rate')),
                  'potencia_media': _num(v.get('avg_power')), 'potencia_max': _num(v.get('max_power')),
                  'np': _num(v.get('normalized_power')), 'tss': _num(v.get('training_stress_score')),
                  'calorias': _num(v.get('total_calories'))}
        break
    return {'puntos': puntos, 'nombre': None, 'tipo': tipo, 'sesion': {k: x for k, x in sesion.items() if x is not None}}


# ---------------------------------------------------------------- resumen

def _haversine(a, b):
    r = 6371000.0
    f1, f2 = math.radians(a['lat']), math.radians(b['lat'])
    df, dl = f2 - f1, math.radians(b['lon'] - a['lon'])
    h = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _desnivel(alturas):
    """Suma de subidas con la altura suavizada (mediana de 5) y sin contar oscilaciones de menos de 3 m."""
    xs = [a for a in alturas if a is not None]
    if len(xs) < 2:
        return None
    suav = [sorted(xs[max(0, i - 2):i + 3])[len(xs[max(0, i - 2):i + 3]) // 2] for i in range(len(xs))]
    total, ref = 0.0, suav[0]
    for a in suav[1:]:
        if a >= ref + UMBRAL_DESNIVEL:
            total, ref = total + a - ref, a
        elif a <= ref - UMBRAL_DESNIVEL:
            ref = a
    return total


def _potencias(puntos):
    """(media, máxima, NP, mejor media de 20 min) con la potencia a 1 s; None si el fichero no la trae."""
    con = [(p['t'], p['pot']) for p in puntos if p['pot'] is not None]
    if len(con) < 30:
        return None, None, None, None
    import pandas as pd
    s = pd.Series([x for _, x in con], index=pd.DatetimeIndex([t for t, _ in con])).groupby(level=0).mean()
    s = s.resample('1s').mean().interpolate(limit=5).fillna(0)
    np_ = float((s.rolling(30).mean().dropna() ** 4).mean() ** 0.25) if len(s) >= 30 else None
    p20 = float(s.rolling(1200).mean().max()) if len(s) >= 1200 else None
    return float(s.mean()), float(s.max()), np_, p20


def resumir(d):
    """Resumen de una actividad leída: fecha local de inicio, km, horas, desnivel, FC y potencia."""
    pts = sorted(d['puntos'], key=lambda p: p['t'])
    ses = d['sesion']
    if not pts and not ses.get('inicio'):
        raise ErrorFichero('El fichero no tiene puntos con hora: no es una actividad grabada (¿es un track planificado?).')
    inicio = ses.get('inicio') or pts[0]['t']
    # distancia: la acumulada del fichero si la trae; si no, la suma entre puntos con posición
    dist = [p.get('dist') for p in pts if p.get('dist') is not None]
    tramos, m, mov = [], 0.0, 0.0
    for a, b in zip(pts, pts[1:]):
        dt = (b['t'] - a['t']).total_seconds()
        if a.get('dist') is not None and b.get('dist') is not None:
            ds = max(b['dist'] - a['dist'], 0)
        elif None not in (a['lat'], a['lon'], b['lat'], b['lon']):
            ds = _haversine(a, b)
            if dt > 0 and ds / dt < VEL_MIN:
                ds = 0
        else:
            ds = 0
        m += ds
        if dt > 0 and (ds / dt >= VEL_MIN or (b['pot'] or 0) > 0):
            mov += min(dt, 60)
        tramos.append(dt)
    km = ses.get('km', dist[-1] - dist[0] if len(dist) > 1 else m) / 1000
    total = (pts[-1]['t'] - pts[0]['t']).total_seconds() if len(pts) > 1 else 0
    fc = [p['fc'] for p in pts if p['fc']]
    pm, pmax, np_, p20 = _potencias(pts)
    r = {'fecha': _local(inicio), 'km': km, 'h': ses.get('h', mov) / 3600, 'h_total': ses.get('h_total', total) / 3600,
         'desnivel': ses.get('desnivel', _desnivel([p['ele'] for p in pts])),
         'fc_media': ses.get('fc_media', sum(fc) / len(fc) if fc else None), 'fc_max': ses.get('fc_max', max(fc) if fc else None),
         'potencia_media': ses.get('potencia_media', pm), 'potencia_max': ses.get('potencia_max', pmax),
         'np': ses.get('np', np_), 'p20': p20, 'tss': ses.get('tss'), 'calorias': ses.get('calorias')}
    if r['h'] <= 0 and r['h_total'] <= 0:
        raise ErrorFichero('La actividad no tiene duración.')
    gps = any(p['lat'] is not None for p in pts)
    tipo = d['tipo'] or ('Ciclismo' if gps else 'Otros')
    if tipo.startswith('Ciclismo') and not gps and tipo not in ('Ciclismo virtual', 'Ciclismo en sala'):
        tipo = 'Ciclismo en sala'
    r['tipo'] = tipo
    return r


def leer(ruta, nombre_original):
    """Lee un fichero (admite .gz) y devuelve su resumen. ErrorFichero si no se puede."""
    base = nombre_original.lower()
    comprimido = base.endswith('.gz')
    if comprimido:
        base = base[:-3]
    ext = os.path.splitext(base)[1]
    if ext not in EXTENSIONES:
        raise ErrorFichero('Formato no admitido: sube ficheros GPX, FIT o TCX.')
    origen = ruta
    if comprimido:
        origen = ruta + '.sin_gz'
        with gzip.open(ruta, 'rb') as e, open(origen, 'wb') as s:
            shutil.copyfileobj(e, s)
    try:
        d = {'.gpx': leer_gpx, '.tcx': leer_tcx, '.fit': leer_fit}[ext](origen)
    except ErrorFichero:
        raise
    except Exception as e:
        raise ErrorFichero(f'No se ha podido leer ({type(e).__name__}).')
    finally:
        if comprimido and os.path.exists(origen):
            os.remove(origen)
    r = resumir(d)
    titulo = d['nombre'] or os.path.splitext(os.path.basename(base))[0].replace('_', ' ')
    r['titulo'] = ' '.join(titulo.split())[:100]
    r['ext'] = ext
    return r


# ---------------------------------------------------------------- almacén

def _csv():
    if not os.path.exists(CSV):
        return []
    with open(CSV, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _guardar(filas):
    os.makedirs(os.path.dirname(CSV), exist_ok=True)
    with open(CSV + '.tmp', 'w', newline='', encoding='utf-8') as f:
        e = csv.DictWriter(f, CAMPOS)
        e.writeheader()
        e.writerows(sorted(filas, key=lambda x: x['fecha']))
    os.replace(CSV + '.tmp', CSV)


def actividades():
    """Filas del CSV de actividades locales (texto)."""
    return _csv()


def huella():
    return os.path.getmtime(CSV) if os.path.exists(CSV) else 0


def _nuevo_id(fecha, usados):
    base = 'L' + fecha.strftime('%Y%m%d%H%M%S')
    aid, n = base, 2
    while aid in usados:
        aid, n = f'{base}-{n}', n + 1
    return aid


def _fmt(v, d=1):
    return '' if v is None else f'{v:.{d}f}'


def limpiar_pendientes(horas=24):
    if not os.path.isdir(PENDIENTES):
        return
    for x in os.listdir(PENDIENTES):
        r = os.path.join(PENDIENTES, x)
        if time.time() - os.path.getmtime(r) > horas * 3600:
            shutil.rmtree(r, ignore_errors=True)


def preparar(ficheros, existentes):
    """ficheros: [(nombre original, objeto con .save(ruta))]. existentes: DataFrame del histórico (fecha, fin, titulo, bici).
    Lee cada fichero y deja el lote en pendientes/<lote>/. Devuelve (lote, filas para revisar)."""
    limpiar_pendientes()
    lote = uuid.uuid4().hex
    carpeta = os.path.join(PENDIENTES, lote)
    os.makedirs(carpeta)
    filas, vistos = [], []
    for i, (nombre, f) in enumerate(ficheros):
        nombre = os.path.basename(nombre or f'fichero{i}')
        ruta = os.path.join(carpeta, f'{i}')
        f.save(ruta)
        fila = {'n': i, 'nombre': nombre}
        try:
            r = leer(ruta, nombre)
        except ErrorFichero as e:
            fila['error'] = str(e)
            os.remove(ruta)
            filas.append(fila)
            continue
        ini = r['fecha']
        fin = ini + _horas(r['h_total'] or r['h'])
        r['fin'] = fin
        # coincide con otra actividad (de Garmin, ya subida o de este mismo lote): por defecto no se importa
        choca = None
        if existentes is not None and len(existentes):
            e = existentes[(existentes.fecha < fin) & (existentes.fin > ini)]
            if len(e):
                choca = f"{e.iloc[0].titulo or 'actividad'} ({e.iloc[0].fecha:%d/%m/%Y %H:%M})"
        for v in vistos:
            if v['fecha'] < fin and v['fin'] > ini:
                choca = f"{v['nombre']}, en este mismo envío"
        fila.update(r, choca=choca, importar=not choca)
        vistos.append({'fecha': ini, 'fin': fin, 'nombre': nombre})
        filas.append(fila)
    with open(os.path.join(carpeta, 'lote.json'), 'w', encoding='utf-8') as f:
        json.dump([{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in x.items()} for x in filas], f, ensure_ascii=False)
    return lote, filas


def _horas(h):
    from datetime import timedelta
    return timedelta(hours=h or 0)


def leer_lote(lote):
    if not re.fullmatch(r'[0-9a-f]{32}', lote or ''):
        return None
    ruta = os.path.join(PENDIENTES, lote, 'lote.json')
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding='utf-8') as f:
        filas = json.load(f)
    for x in filas:
        for k in ('fecha', 'fin'):
            if x.get(k):
                x[k] = datetime.fromisoformat(x[k])
    return filas


def descartar(lote):
    if re.fullmatch(r'[0-9a-f]{32}', lote or ''):
        shutil.rmtree(os.path.join(PENDIENTES, lote), ignore_errors=True)


def confirmar(lote, elegidas):
    """elegidas: {n: {'tipo', 'titulo'}} de las filas que se importan. Guarda los originales y el resumen.
    Devuelve [(id, fila)] de lo importado."""
    filas = leer_lote(lote)
    if filas is None:
        raise ErrorFichero('El envío ha caducado o ya se ha importado: vuelve a subir los ficheros.')
    actuales = _csv()
    usados = {x['id'] for x in actuales}
    hechas = []
    for x in filas:
        e = elegidas.get(x['n'])
        if e is None or x.get('error'):
            continue
        aid = _nuevo_id(x['fecha'], usados)
        usados.add(aid)
        destino = os.path.join(CARPETA, f"{x['fecha']:%Y}")
        os.makedirs(destino, exist_ok=True)
        fichero = f"{aid}{x['ext']}" + ('.gz' if x['nombre'].lower().endswith('.gz') else '')
        shutil.move(os.path.join(PENDIENTES, lote, str(x['n'])), os.path.join(destino, fichero))
        tipo = e['tipo'] if e['tipo'] in TIPOS else x['tipo']
        titulo = ' '.join((e.get('titulo') or x['titulo']).split())[:100]
        fila = {'id': aid, 'fecha': x['fecha'].isoformat(timespec='seconds'), 'tipo': tipo, 'titulo': titulo,
                'km': _fmt(x['km'], 3), 'h': _fmt(x['h'], 5), 'h_total': _fmt(x['h_total'], 5), 'desnivel': _fmt(x['desnivel'], 0),
                'fc_media': _fmt(x['fc_media'], 0), 'fc_max': _fmt(x['fc_max'], 0), 'potencia_media': _fmt(x['potencia_media'], 0),
                'potencia_max': _fmt(x['potencia_max'], 0), 'np': _fmt(x['np'], 0), 'p20': _fmt(x['p20'], 0), 'tss': _fmt(x['tss'], 1),
                'calorias': _fmt(x['calorias'], 0), 'fichero': f"{x['fecha']:%Y}/{fichero}",
                'importada': datetime.now().isoformat(timespec='seconds')}
        actuales.append(fila)
        hechas.append((aid, {**x, 'tipo': tipo, 'titulo': titulo}))
    _guardar(actuales)
    descartar(lote)
    return hechas


def renombrar(aid, nombre):
    filas = _csv()
    for x in filas:
        if x['id'] == aid:
            x['titulo'] = nombre
            _guardar(filas)
            return True
    return False


def borrar(aid):
    """Quita una actividad subida a mano y su fichero original."""
    filas = _csv()
    x = next((x for x in filas if x['id'] == aid), None)
    if x is None:
        return False
    _guardar([y for y in filas if y['id'] != aid])
    ruta = os.path.join(CARPETA, x['fichero'])
    if x['fichero'] and os.path.exists(ruta):
        os.remove(ruta)
    return True


def leer_puntos(ruta):
    """Puntos de un fichero GPX, FIT o TCX (admite .gz) con la distancia acumulada en km: [(km, altitud, lat, lon)]."""
    base = ruta.lower()
    comprimido = base.endswith('.gz')
    ext = os.path.splitext(base[:-3] if comprimido else base)[1]
    origen = ruta
    if comprimido:
        origen = ruta + '.sin_gz'
        with gzip.open(ruta, 'rb') as e, open(origen, 'wb') as s:
            shutil.copyfileobj(e, s)
    try:
        pts = sorted({'.gpx': leer_gpx, '.tcx': leer_tcx, '.fit': leer_fit}[ext](origen)['puntos'], key=lambda p: p['t'])
    finally:
        if comprimido and os.path.exists(origen):
            os.remove(origen)
    r, m, ant = [], 0.0, None
    for p in pts:
        if p.get('dist') is not None:
            m = p['dist']
        elif ant is not None and None not in (ant['lat'], ant['lon'], p['lat'], p['lon']):
            m += _haversine(ant, p)
        if p['lat'] is not None or p.get('dist') is not None:
            ant = p if p['lat'] is not None else ant
        r.append((m / 1000, p['ele'], p['lat'], p['lon']))
    return r


def puntos(aid):
    """Puntos de una actividad subida a mano; [] si no se encuentra su fichero."""
    x = next((x for x in _csv() if x['id'] == aid), None)
    ruta = os.path.join(CARPETA, x['fichero']) if x and x.get('fichero') else ''
    return leer_puntos(ruta) if ruta and os.path.exists(ruta) else []

