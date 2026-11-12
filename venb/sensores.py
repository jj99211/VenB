"""Validador de sesiones: tramos sin datos de los sensores (pulsómetro, potencia, cadencia, velocidad, GPS).

Para cada actividad con registros (FIT descargado de Garmin o fichero importado) se mira, sensor por sensor, el tiempo en
que el sensor existe en la sesión pero no da datos o los da congelados, en cortes de 5 s o más:
- pulsómetro: sin dato o 0, o el mismo valor durante 2 min o más (congelado);
- potencia: sin dato (en rodillo, también 0 W: allí no se rueda sin pedalear);
- cadencia: sin dato, o 0 mientras la potencia pasa de 80 W (pedaleando);
- velocidad: sin dato, o 0 mientras se pedalea con fuerza (potencia ≥ 80 W o cadencia ≥ 40);
- GPS (solo en exterior): sin posición.
Los ceros normales (cadencia 0 en una bajada, velocidad 0 parado) no cuentan. Si un sensor deja de enviar a mitad de la
sesión y no vuelve, se dice a qué minuto (indicio de batería). Si falta en toda la sesión pero estaba en al menos 3 de
las 5 sesiones anteriores del mismo tipo (rodillo o exterior), se avisa (indicio de emparejamiento o configuración).
Resultados en caché: VenB-datos/datos/sensores_cache.json.
"""
import gzip
import json
import os
import shutil
import tempfile
from datetime import date, timedelta

import rutas

VERSION = 1
CACHE = os.path.join(rutas.DATOS, 'sensores_cache.json')
CORTE_MIN_S = 5            # cortes más breves no cuentan
CONGELADO_S = 120          # pulsómetro con el mismo valor durante este tiempo: congelado
TRAMO_DIBUJO_S = 30        # tramos que se marcan sobre el perfil
NOMBRE = {'fc': 'el pulsómetro', 'potencia': 'el potenciómetro', 'cadencia': 'el sensor de cadencia',
          'velocidad': 'el sensor de velocidad', 'gps': 'el GPS'}
CORTO = {'fc': 'pulso', 'potencia': 'potencia', 'cadencia': 'cadencia', 'velocidad': 'velocidad', 'gps': 'GPS'}


# ---------------------------------------------------------------- lectura de registros

def _fit(ruta):
    import fitparse
    f = fitparse.FitFile(ruta)
    r = []
    for m in f.get_messages('record'):
        v = m.get_values()
        if not v.get('timestamp'):
            continue
        vel = v.get('enhanced_speed', v.get('speed'))
        r.append({'t': v['timestamp'], 'fc': v.get('heart_rate'), 'potencia': v.get('power'), 'cadencia': v.get('cadence'),
                  'velocidad': vel, 'gps': v.get('position_lat'), 'dist': v.get('distance')})
    return r


def _importada(aid):
    """Registros de una actividad subida a mano (FIT con todos los sensores; GPX/TCX, pulso, potencia y GPS)."""
    import importar
    x = next((x for x in importar._csv() if x['id'] == aid), None)
    ruta = os.path.join(importar.CARPETA, x['fichero']) if x and x.get('fichero') else ''
    if not ruta or not os.path.exists(ruta):
        return []
    base = ruta.lower()
    tmp = None
    if base.endswith('.gz'):
        tmp = tempfile.NamedTemporaryFile(suffix=os.path.splitext(base[:-3])[1], delete=False)
        with gzip.open(ruta, 'rb') as e:
            shutil.copyfileobj(e, tmp)
        tmp.close()
        ruta, base = tmp.name, base[:-3]
    try:
        if base.endswith('.fit'):
            return _fit(ruta)
        pts = (importar.leer_gpx if base.endswith('.gpx') else importar.leer_tcx)(ruta)['puntos']
        return [{'t': p['t'], 'fc': p.get('fc'), 'potencia': p.get('pot'), 'cadencia': None, 'velocidad': None,
                 'gps': p.get('lat'), 'dist': None} for p in sorted(pts, key=lambda p: p['t'])]
    finally:
        if tmp:
            os.remove(tmp.name)


def registros(aid):
    import importar
    aid = str(aid)
    if importar.ES_ID.fullmatch(aid):
        return _importada(aid)
    fit = os.path.join(rutas.ruta_garmin(), f'{aid}_ACTIVITY.fit')
    return _fit(fit) if os.path.exists(fit) else []


# ---------------------------------------------------------------- análisis

def _falta(s, r, virtual):
    v = r[s]
    if s == 'fc':
        return not v
    if s == 'potencia':
        return v is None or (virtual and v == 0)
    if s == 'cadencia':
        return v is None or (v == 0 and (r['potencia'] or 0) >= 80)
    if s == 'velocidad':
        return v is None or (v == 0 and ((r['potencia'] or 0) >= 80 or (r['cadencia'] or 0) >= 40))
    return v is None    # gps


def analizar(regs, virtual):
    """{'dur': s, 'presentes': [...], 'sensores': {s: {'pct', 'final_min' (o None), 'tramos': [[ini_s, fin_s, km0, km1]]}}}."""
    if len(regs) < 10:
        return {'dur': 0, 'presentes': [], 'sensores': {}}
    t0 = regs[0]['t']
    seg = [(r['t'] - t0).total_seconds() for r in regs]
    dur = [max(0.0, min(seg[i + 1] - seg[i], 10.0)) for i in range(len(seg) - 1)] + [1.0]   # pausas largas: fuera
    total = sum(dur) or 1.0
    dist = [r['dist'] for r in regs]
    hay_dist = any(d for d in dist)
    km_total = (max(d for d in dist if d) / 1000) if hay_dist else None

    def km(i):
        if hay_dist:
            d = next((dist[j] for j in range(i, -1, -1) if dist[j] is not None), 0)
            return round((d or 0) / 1000, 3)
        return None

    sensores = ['fc', 'potencia', 'cadencia', 'velocidad'] + ([] if virtual else ['gps'])
    salida = {'dur': round(total), 'presentes': [], 'sensores': {}, 'km': km_total}
    for s in sensores:
        if not any(r[s] for r in regs):
            continue      # el sensor no está en esta sesión
        salida['presentes'].append(s)
        falta = [_falta(s, r, virtual) for r in regs]
        if s == 'fc':     # congelado: el mismo valor durante 2 min o más
            i = 0
            while i < len(regs):
                j, acum = i, 0.0
                while j + 1 < len(regs) and regs[j + 1]['fc'] == regs[i]['fc'] and regs[i]['fc']:
                    acum += dur[j]
                    j += 1
                if acum >= CONGELADO_S:
                    for k in range(i, j + 1):
                        falta[k] = True
                i = j + 1
        tramos, perdido, i = [], 0.0, 0
        while i < len(regs):
            if not falta[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(regs) and falta[j + 1]:
                j += 1
            t = sum(dur[i:j + 1])
            if t >= CORTE_MIN_S:
                perdido += t
                if t >= TRAMO_DIBUJO_S:
                    tramos.append([round(seg[i]), round(seg[j] + dur[j]), km(i), km(j)])
            i = j + 1
        final = None
        if tramos and tramos[-1][1] >= total - 15 and tramos[-1][0] > 0.02 * total and tramos[-1][1] - tramos[-1][0] >= 300:
            final = round(tramos[-1][0] / 60)
        salida['sensores'][s] = {'pct': round(100 * perdido / total, 1), 'final_min': final, 'tramos': tramos[:60]}
    return salida


# ---------------------------------------------------------------- caché y avisos

def _leer_cache():
    try:
        with open(CACHE, encoding='utf-8') as f:
            c = json.load(f)
        return c if c.get('version') == VERSION else {'version': VERSION}
    except (OSError, ValueError):
        return {'version': VERSION}


def _guardar_cache(c):
    with open(CACHE + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(c, f)
    os.replace(CACHE + '.tmp', CACHE)


def de_actividad(aid, virtual, cache=None):
    """Análisis de una actividad (con caché). None si no hay registros."""
    c = cache if cache is not None else _leer_cache()
    aid = str(aid)
    if aid not in c:
        try:
            regs = registros(aid)
        except Exception:
            regs = []
        c[aid] = analizar(regs, virtual) if regs else None
        if cache is None:
            _guardar_cache(c)
    return c[aid]


def problemas(x, sensores_vigilar, pct_min, habituales=()):
    """[(sensor, texto)] de un análisis: cortes por encima de pct_min %, corte final y sensores que faltan y suelen estar."""
    r = []
    if not x:
        return r
    gps = x['sensores'].get('gps')
    for s, d in x['sensores'].items():
        if s not in sensores_vigilar:
            continue
        if s == 'velocidad' and gps and 'gps' in sensores_vigilar and abs(gps['pct'] - d['pct']) < 1:
            continue      # en exterior, la velocidad sale del GPS: basta con avisar de este
        if d['final_min'] is not None:
            r.append((s, f"{NOMBRE[s]} dejó de enviar datos a los {d['final_min']} min" + (' (¿batería?)' if s != 'gps' else '')))
        elif d['pct'] >= pct_min:
            r.append((s, f"{CORTO[s]} sin datos el {str(d['pct']).replace('.', ',')} % del tiempo"))
    for s in habituales:
        if s in sensores_vigilar and s not in x['presentes']:
            r.append((s, f"sin datos de {CORTO[s]} en toda la sesión, aunque suele haberlos (¿sensor sin emparejar o apagado?)"))
    return r


def revisar(df, dias, sensores_vigilar, pct_min, hoy=None, calcular=True):
    """Sesiones de los últimos `dias` con problemas: [{'id', 'fecha', 'titulo', 'problemas': [(sensor, texto)]}].
    Con calcular=False solo usa lo que ya está en caché (para no hacer esperar a Inicio)."""
    hoy = hoy or date.today()
    c = _leer_cache()
    antes = len(c)
    d = df.rename(columns={'Título': 'titulo', 'Tipo de actividad': 'tipo_act'}).sort_values('Fecha')
    salida = []
    for _, g in d.groupby('tipo_act'):
        filas = list(g.itertuples())
        for n, a in enumerate(filas):
            if a.Fecha.date() < hoy - timedelta(days=dias):
                continue
            virtual = bool(getattr(a, 'virtual', False))
            x = de_actividad(a.id, virtual, c) if calcular else c.get(str(a.id))
            if not x:
                continue
            # sensores habituales: presentes en al menos 3 de las 5 sesiones anteriores del mismo tipo con registros
            previas = [de_actividad(p.id, bool(getattr(p, 'virtual', False)), c) if calcular else c.get(str(p.id))
                       for p in filas[max(0, n - 8):n]]
            previas = [p for p in previas if p][-5:]
            habituales = [s for s in NOMBRE if sum(s in p['presentes'] for p in previas) >= 3] if len(previas) >= 3 else []
            pr = problemas(x, sensores_vigilar, pct_min, habituales)
            if pr:
                salida.append({'id': str(a.id), 'fecha': a.Fecha.date(), 'titulo': a.titulo if isinstance(a.titulo, str) else '', 'problemas': pr})
    if len(c) != antes:
        _guardar_cache(c)
    return sorted(salida, key=lambda s: s['fecha'])


_hilo = {}


def revisar_en_segundo_plano(df, dias, sensores_vigilar, pct_min):
    """Analiza en un hilo las sesiones que aún no están en caché (leer un FIT tarda alrededor de un segundo)."""
    import threading
    h = _hilo.get('h')
    if h and h.is_alive():
        return
    _hilo['h'] = threading.Thread(target=revisar, args=(df, dias, sensores_vigilar, pct_min), daemon=True)
    _hilo['h'].start()
