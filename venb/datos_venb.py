"""Lectura de datos para VenB. Los cálculos de carga vienen de scripts/carga.py."""
import csv, glob, hashlib, json, os, re, shutil, sqlite3, subprocess, sys, time, urllib.request, uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
PROYECTO = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(PROYECTO, 'scripts'))
from carga import cargar, leer_garmin, leer_locales  # noqa: E402
import rutas  # noqa: E402
import bicis  # noqa: E402
import garmin_freno as FR  # noqa: E402
import importar  # noqa: E402

DATOS, INFORMES, ESTADO, CAL_URL = rutas.DATOS, rutas.INFORMES, rutas.ESTADO, rutas.CAL_URL
EVENTOS = os.path.join(DATOS, 'eventos.json')
PESO = os.path.join(DATOS, 'peso.csv')
CAL_CACHE = os.path.join(DATOS, 'calendario_cache.ics')  # el de Randonneurs (u otro por defecto)
CAL_CACHE_PROPIO = os.path.join(DATOS, 'calendario_propio_cache.ics')
MES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
TIPOS = {'cycling': 'Ciclismo', 'road_biking': 'Ciclismo en ruta', 'virtual_ride': 'Ciclismo virtual', 'indoor_cycling': 'Ciclismo en sala',
         'mountain_biking': 'Ciclismo de montaña', 'gravel_cycling': 'Gravel', 'running': 'Carrera', 'walking': 'Caminar', 'casual_walking': 'Caminar',
         'speed_walking': 'Caminar', 'hiking': 'Senderismo', 'other': 'Otros', 'indoor_cardio': 'Cardio en sala'}
BICI = {'Ciclismo', 'Ciclismo en ruta', 'Ciclismo virtual', 'Ciclismo en sala', 'Ciclismo de montaña', 'Gravel'}
_cache = {}


def _uri_garmin():
    """Solo lectura; as_uri también resuelve las rutas de Windows."""
    return Path(rutas.ruta_garmin_db()).as_uri() + '?mode=ro'


def _huella():
    """Cambia cuando llegan actividades nuevas o cambia el día."""
    fs = glob.glob(os.path.join(rutas.ruta_garmin(), 'activity_[0-9]*.json'))
    return date.today(), len(fs), max((os.path.getmtime(f) for f in fs), default=0), importar.huella()


def carga():
    """(actividades, pmc) con el método validado; se recalcula solo si hay datos nuevos."""
    h = _huella()
    if _cache.get('huella') != h:
        df, pmc, _ = cargar('garmin', pd.Timestamp.today().normalize())
        _cache.update(huella=h, df=df, pmc=pmc, hist=None)
    return _cache['df'], _cache['pmc']


def historico():
    """Actividades desde 2008: exportación + descargas nuevas, sin duplicados ni solapes de bici."""
    try:
        carga()
    except Exception:
        pass  # sin Garmin todavía: basta con la exportación, si la hay
    if _cache.get('hist') is not None:
        return _cache['hist']
    filas = []
    ruta = os.path.join(DATOS, 'historico_actividades.csv')
    if os.path.exists(ruta):
        e = pd.read_csv(ruta, dtype={'id': str})
        e['fecha'] = pd.to_datetime(e.fecha)
        e['tipo'] = e.tipo.map(lambda t: TIPOS.get(t, t))
        filas.append(e)
    try:
        g = leer_garmin()
        filas.append(pd.DataFrame({'id': g.id.astype(str).str.replace(r'\.0$', '', regex=True), 'fecha': g.Fecha, 'tipo': g['Tipo de actividad'].map(lambda t: TIPOS.get(t, t)),
                                   'titulo': g['Título'], 'km': g.Distancia, 'h': g.h, 'h_total': g.h_total, 'desnivel': g['Ascenso total']}))
    except FileNotFoundError:
        pass
    loc = leer_locales()
    if len(loc):
        filas.append(pd.DataFrame({'id': loc.id, 'fecha': loc.Fecha, 'tipo': loc['Tipo de actividad'], 'titulo': loc['Título'], 'km': loc.Distancia,
                                   'h': loc.h, 'h_total': loc.h_total, 'desnivel': loc['Ascenso total']}))
    if not filas:
        return pd.DataFrame()
    d = pd.concat(filas).drop_duplicates('id', keep='last').sort_values('fecha').reset_index(drop=True)
    d['fin'] = d.fecha + pd.to_timedelta(d.h_total.fillna(d.h).fillna(0), unit='h')
    b = d[d.tipo.isin(BICI)]
    idx, ini, fin, km = list(b.index), list(b.fecha), list(b.fin), list(b.km)
    fuera = set()
    for x, i in enumerate(idx):
        for y in range(x + 1, len(idx)):
            if not ini[y] < fin[x] or i in fuera:
                break
            j = idx[y]
            if j not in fuera and ini[x] < fin[y]:
                fuera.add(i if km[x] < km[y] else j)
    d = d.drop(index=list(fuera))
    d['bici'] = d.tipo.isin(BICI)
    d['titulo'] = d.titulo.fillna('')
    _cache['hist'] = d
    _cache['hist_dups'] = len(fuera)
    return d


def resumen_semana(df, lunes):
    b = df[df.bici & (df.Fecha >= lunes) & (df.Fecha < lunes + pd.Timedelta(days=7))]
    return {'h': float(b.h.sum()), 'km': float(b.Distancia.sum()), 'n': len(b)}


def salud(dias=7):
    """Medias recientes de sueño, VFC y FC en reposo; None si la base no está disponible."""
    try:
        c = sqlite3.connect(_uri_garmin(), uri=True, timeout=2)
        desde =(date.today() - timedelta(days=dias)).isoformat()
        s = pd.read_sql('select day,total_sleep,score from sleep where day>=?', c, params=(desde,))
        h = pd.to_timedelta(s.total_sleep.str.slice(0, 8)).dt.total_seconds() / 3600
        h = h[h > 0]
        fc = pd.read_sql('select avg(resting_heart_rate) v from resting_hr where day>=?', c, params=(desde,)).v[0]
        vfc = pd.read_sql('select avg(last_night_avg) v from hrv where day>=?', c, params=(desde,)).v[0]
        ultimo = pd.read_sql('select max(day) v from hrv', c).v[0]
        c.close()
        return {'h': h.mean() if len(h) else None, 'score': s.score.mean() if len(s) else None, 'noches': len(h), 'fc': fc, 'vfc': vfc,
                'ultimo': pd.Timestamp(ultimo).date() if ultimo else None}
    except Exception:
        return None


# ---------- Series para las gráficas ----------
def _lista(s, d=1):
    return [None if pd.isna(x) else round(float(x), d) for x in s]


def _dias(idx):
    return [f'{x:%Y-%m-%d}' for x in idx]


def _salud_diaria():
    """Medias móviles de 7 días de sueño, VFC y FC en reposo, por día."""
    vacio = {'f': [], 'sueno': [], 'vfc': [], 'fc': []}
    try:
        c = sqlite3.connect(_uri_garmin(), uri=True, timeout=2)
        s = pd.read_sql('select day,total_sleep from sleep', c, parse_dates=['day']).set_index('day')
        f = pd.read_sql('select day,resting_heart_rate v from resting_hr', c, parse_dates=['day']).set_index('day')
        v = pd.read_sql('select day,last_night_avg v from hrv', c, parse_dates=['day']).set_index('day')
        c.close()
    except Exception:
        return vacio
    h = pd.to_timedelta(s.total_sleep.str.slice(0, 8)).dt.total_seconds() / 3600
    h = h[h > 0]
    if not len(h):
        return vacio
    dias = pd.date_range(min(h.index.min(), f.index.min(), v.index.min()), max(h.index.max(), f.index.max(), v.index.max()))
    media = lambda x: x[~x.index.duplicated()].reindex(dias).rolling(7, min_periods=3).mean()
    return {'f': _dias(dias), 'sueno': _lista(media(h), 2), 'vfc': _lista(media(v.v), 1), 'fc': _lista(media(f.v), 1)}


def graficas():
    """Todas las series de la página Gráficas, ya agregadas. Se calculan con carga() e historico()."""
    try:
        df, pmc = carga()
    except Exception:
        df, pmc = None, None
    d = historico()
    if d.empty:
        raise LookupError('sin actividades')
    b = d[d.bici].dropna(subset=['fecha'])
    hoy = pd.Timestamp.today().normalize()
    # Semanas (lunes)
    x = b.set_index('fecha')[['h', 'km']].fillna(0)
    lunes = x.index.normalize() - pd.to_timedelta(x.index.weekday, unit='D')
    sem = x.groupby(lunes).sum()
    rango = pd.date_range(sem.index.min(), hoy - pd.Timedelta(days=hoy.weekday()), freq='7D')
    sem = sem.reindex(rango, fill_value=0)
    # Año
    anios = range(int(b.fecha.dt.year.min()), hoy.year + 1)
    an = b.groupby(b.fecha.dt.year).agg(km=('km', 'sum'), h=('h', 'sum'), n=('km', 'size'), desnivel=('desnivel', 'sum')).reindex(anios, fill_value=0)
    # Año × mes
    mapa = b.pivot_table(index=b.fecha.dt.year, columns=b.fecha.dt.month, values='km', aggfunc='sum', fill_value=0).reindex(index=anios, columns=range(1, 13), fill_value=0)
    # Acumulado sobre una rejilla de año bisiesto, para comparar años entre sí
    rej = pd.date_range('2024-01-01', '2024-12-31')
    claves = rej.strftime('%m-%d')
    acum = []
    diario = b.groupby(b.fecha.dt.normalize()).km.sum()
    for a in range(hoy.year - 4, hoy.year + 1):
        dias = pd.date_range(f'{a}-01-01', f'{a}-12-31')
        s = diario.reindex(dias, fill_value=0).cumsum()
        s = s.where(dias <= hoy)
        s.index = dias.strftime('%m-%d')
        s = s.reindex(claves)
        if a % 4:  # el 29 de febrero no existe: repite el día anterior
            s.loc['02-29'] = s.loc['02-28']
        acum.append({'a': a, 'km': _lista(s, 0)})
    # Distancias
    tramos = rutas.ajustes()['tramos_salidas']
    etiq = [t[0] for t in tramos]
    dist = pd.cut(b.km[b.km > 0], [t[1] for t in tramos] + [tramos[-1][2]], labels=etiq, right=False).value_counts().reindex(etiq, fill_value=0)
    # Mejor potencia de 20 min por mes, en las actividades que la registran
    pot = pd.Series(dtype=float)
    if df is not None:
        pot = df[df.bici & (df['Potencia media máxima (20 minutos)'] > 0)]
        pot = pot.groupby(pot.Fecha.dt.to_period('M'))['Potencia media máxima (20 minutos)'].max()
    p = pesos()
    return {'hoy': f'{hoy:%Y-%m-%d}', 'sueno_ref': rutas.ajustes()['sueno_referencia_h'],
            'pmc': {'f': _dias(pmc.index), 'CTL': _lista(pmc.CTL), 'ATL': _lista(pmc.ATL), 'TSB': _lista(pmc.TSB)} if pmc is not None else {'f': [], 'CTL': [], 'ATL': [], 'TSB': []},
            'semanas': [{'f': f'{i:%Y-%m-%d}', 'h': round(float(r.h), 2), 'km': round(float(r.km), 1)} for i, r in sem.iterrows()],
            'potencia': {'f': [f'{i}-01' for i in pot.index], 'w': _lista(pot, 0)},
            'salud': _salud_diaria(),
            'peso': {'f': [a for a, _ in p], 'kg': [k for _, k in p]},
            'anual': {'a': list(anios), 'km': _lista(an.km, 0), 'h': _lista(an.h, 0), 'n': [int(v) for v in an.n], 'desnivel': _lista(an.desnivel, 0)},
            'acumulado': {'f': _dias(rej), 'series': acum},
            'mapa': {'anios': list(anios), 'km': [_lista(mapa.loc[a], 0) for a in anios]},
            'distancias': {'et': etiq, 'n': [int(v) for v in dist]}}


def tendencias(g):
    """Últimas 12 semanas de cada indicador, para las líneas pequeñas de Inicio."""
    cada7 = lambda v: v[-78::7] if len(v) >= 78 else v[::7]
    return {'ctl': cada7(g['pmc']['CTL']), 'atl': cada7(g['pmc']['ATL']), 'tsb': cada7(g['pmc']['TSB']),
            'horas': [s['h'] for s in g['semanas'][-12:]],
            'sueno': cada7(g['salud']['sueno']), 'vfc': cada7(g['salud']['vfc']), 'fc': cada7(g['salud']['fc']),
            'peso': g['peso']['kg'][-12:], 'km_mes': _km_meses(g)[-12:], 'potencia': g['potencia']['w'][-12:]}


def _km_meses(g):
    """Km de bici de cada mes hasta el actual, a partir del mapa año × mes."""
    hoy = date.today()
    v = [x for a, fila in zip(g['mapa']['anios'], g['mapa']['km']) for x in (fila if a < hoy.year else fila[:hoy.month])]
    return v


def resumen_mes_y_potencia(df, dias=30):
    """Km de bici del mes en curso y del anterior, y mejor potencia de 20 min de los últimos `dias` días con su fecha."""
    hoy = pd.Timestamp.today().normalize()
    b = df[df.bici]
    ini = hoy.replace(day=1)
    ant = (ini - pd.Timedelta(days=1)).replace(day=1)
    km = float(b[b.Fecha >= ini].Distancia.sum())
    km_ant = float(b[(b.Fecha >= ant) & (b.Fecha < ini)].Distancia.sum())
    p = b[(b.Fecha >= hoy - pd.Timedelta(days=dias)) & (b['Potencia media máxima (20 minutos)'] > 0)]
    if p.empty:
        return {'km': km, 'km_ant': km_ant, 'mes_ant': MES[ant.month - 1], 'p20': None, 'p20_fecha': None, 'dias': dias}
    m = p.loc[p['Potencia media máxima (20 minutos)'].idxmax()]
    return {'km': km, 'km_ant': km_ant, 'mes_ant': MES[ant.month - 1], 'p20': float(m['Potencia media máxima (20 minutos)']),
            'p20_fecha': m.Fecha.date(), 'dias': dias}


def km_garmin_mes(mes):
    """Km de bici de un mes AAAA-MM según Garmin. Garmin no indica la bici."""
    try:
        df, _ = carga()
    except Exception:
        return {'exterior': 0, 'rodillo': 0}
    b = df[df.bici & (df.Fecha.dt.strftime('%Y-%m') == mes)]
    return {'exterior': float(b[~b.virtual].Distancia.sum()), 'rodillo': float(b[b.virtual].Distancia.sum())}


def _id(x):
    return str(x).removesuffix('.0')


def salidas_exterior_mes(mes):
    """Salidas de bici en exterior de un mes AAAA-MM, con su bici si está asignada, para repartirlas entre las bicis."""
    try:
        df, _ = carga()
    except Exception:
        return []
    asig = bicis.asignaciones()
    b = df[df.bici & ~df.virtual & (df.Fecha.dt.strftime('%Y-%m') == mes)].sort_values('Fecha')
    return [{'id': _id(x.id), 'fecha': x.Fecha, 'titulo': x['Título'] or '', 'km': float(x.Distancia),
             'asignada': '|'.join(asig[_id(x.id)]) if _id(x.id) in asig else ''} for _, x in b.iterrows()]


def km_asignados_mes(mes):
    """Km de bici de un mes AAAA-MM según la bici asignada a cada actividad.
    Devuelve {'bicis': {(bici, rodadura): km} de las bicis en uso, 'fuera': km de «Otra» y de bicis retiradas
    (no entran en el reparto), 'libre_ext' y 'libre_rod': km sin bici asignada, en exterior y en rodillo}."""
    salida = {'bicis': {}, 'fuera': 0.0, 'libre_ext': 0.0, 'libre_rod': 0.0}
    try:
        df, _ = carga()
    except Exception:
        return salida
    asig, activas = bicis.asignaciones(), {x['id'] for x in bicis.activas()}
    for _, x in df[df.bici & (df.Fecha.dt.strftime('%Y-%m') == mes)].iterrows():
        km = float(x.Distancia or 0)
        a = asig.get(_id(x.id))
        if a is None:
            salida['libre_rod' if x.virtual else 'libre_ext'] += km
        elif a[0] in activas:
            salida['bicis'][a] = salida['bicis'].get(a, 0) + km
        else:
            salida['fuera'] += km
    return salida


def pesos_km_mes(mes, claves, rodillo=None, meses=3):
    """Proporción en que repartiste los km de exterior en los `meses` anteriores con datos: {clave: km}.
    A la casilla del rodillo se le descuentan los km de rodillo de cada mes."""
    filas = [r for r in bicis.km_filas() if r['mes'] < mes]
    previos = sorted({r['mes'] for r in filas}, reverse=True)[:meses]
    pesos = {c: 0.0 for c in claves}
    for m in previos:
        rod = km_garmin_mes(m)['rodillo'] if rodillo else 0
        for r in filas:
            c = (r['bici'], r['rodadura'])
            if r['mes'] == m and c in pesos:
                pesos[c] += max(r['km'] - rod, 0) if c == rodillo else r['km']
    return pesos


def propuesta_km_mes(mes, claves, rodillo=None, meses=3):
    """Reparte los km de exterior del mes entre las casillas (bici, rodadura) en la proporción de los `meses` anteriores
    con datos. A la casilla del rodillo se le descuentan los km de rodillo de cada mes, y en la propuesta se le suman.
    Devuelve {clave: km}; vacío si no hay meses anteriores con km de exterior."""
    filas = [r for r in bicis.km_filas() if r['mes'] < mes]
    previos = sorted({r['mes'] for r in filas}, reverse=True)[:meses]
    pesos = {c: 0.0 for c in claves}
    for m in previos:
        rod = km_garmin_mes(m)['rodillo'] if rodillo else 0
        for r in filas:
            c = (r['bici'], r['rodadura'])
            if r['mes'] == m and c in pesos:
                pesos[c] += max(r['km'] - rod, 0) if c == rodillo else r['km']
    total = sum(pesos.values())
    g = km_garmin_mes(mes)
    if not total or not g['exterior']:
        return {rodillo: round(g['rodillo'])} if rodillo and g['rodillo'] else {}
    salida = {c: round(g['exterior'] * p / total) for c, p in pesos.items()}
    mayor = max(pesos, key=pesos.get)
    salida[mayor] += round(g['exterior']) - sum(salida.values())  # que el redondeo no descuadre el total
    if rodillo:
        salida[rodillo] = salida.get(rodillo, 0) + round(g['rodillo'])
    return salida


# ---------- Peso ----------
def _pesos_garmin():
    """Pesos descargados por garmindb, en kilos. Sin base de datos o sin pesos, ninguno."""
    try:
        c = sqlite3.connect(_uri_garmin(), uri=True, timeout=2)
        try:
            sistema = c.execute("select value from attributes where key='measurement_system'").fetchone()
            filas = c.execute('select day, weight from weight where weight > 0').fetchall()
        finally:
            c.close()
    except sqlite3.Error:
        return {}
    factor = 0.45359237 if sistema and 'statute' in sistema[0] else 1
    return {str(dia)[:10]: round(kg * factor, 1) for dia, kg in filas}


def pesos():
    """Por fecha, lo anotado a mano manda sobre Garmin, y Garmin sobre la exportación importada."""
    filas = {}
    ruta = os.path.join(DATOS, 'peso_historico.csv')
    for r in (ruta, 'garmin', PESO):
        if r == 'garmin':
            filas.update(_pesos_garmin())
        elif os.path.exists(r):
            with open(r, encoding='utf-8') as f:
                for x in csv.DictReader(f):
                    filas[x['fecha']] = float(x['kg'])
    return sorted(filas.items())


def _config_garmin():
    return os.path.join(rutas.GARMIN_CONFIG, 'GarminConnectConfig.json')


def garmindb_configurado():
    return os.path.exists(_config_garmin())


def peso_desde_garmin():
    """El origen del peso se guarda solo en la configuración de garmindb, que es quien lo descarga."""
    if not usar_garmin():
        return False
    try:
        with open(_config_garmin(), encoding='utf-8') as f:
            return bool(json.load(f)['enabled_stats']['weight'])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def elegir_peso_desde_garmin(activar):
    """Cambia solo el peso en esa configuración. Al activarlo pide los últimos 90 días, para no hacer una petición
    a Garmin por cada día desde la fecha de inicio. Devuelve False si no se ha podido cambiar."""
    ruta = _config_garmin()
    try:
        with open(ruta, encoding='utf-8') as f:
            config = json.load(f)
        if bool(config['enabled_stats'].get('weight')) == activar:
            return True
        config['enabled_stats']['weight'] = activar
        if activar:
            config['data']['weight_start_date'] = (date.today() - timedelta(days=90)).strftime('%m/%d/%Y')
        modo = os.stat(ruta).st_mode & 0o777  # contiene credenciales: conserva sus permisos
        descriptor = os.open(ruta + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, modo)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        os.replace(ruta + '.tmp', ruta)
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def anotar_peso(fecha, kg):
    nuevo = not os.path.exists(PESO)
    with open(PESO, 'a', newline='', encoding='utf-8') as f:
        e = csv.writer(f)
        if nuevo:
            e.writerow(['fecha', 'kg'])
        e.writerow([fecha, kg])


# ---------- Usar Garmin Connect (o solo ficheros subidos a mano) ----------
def usar_garmin():
    return bool(rutas.ajustes().get('usar_garmin', True))


def elegir_usar_garmin(activar):
    """Guarda la opción y activa o detiene la descarga diaria programada, si está instalada. Devuelve un aviso o None."""
    rutas.guardar_ajustes({'usar_garmin': bool(activar)})
    try:
        if os.name == 'nt':
            orden = ['schtasks', '/Change', '/TN', 'VenB Garmin', '/ENABLE' if activar else '/DISABLE']
        else:
            if not os.path.exists(os.path.expanduser('~/.config/systemd/user/garmindb.timer')):
                return None
            orden = ['systemctl', '--user', 'enable' if activar else 'disable', '--now', 'garmindb.timer']
        r = subprocess.run(orden, capture_output=True, text=True, timeout=30)
        if r.returncode and os.name != 'nt':
            return 'No se ha podido cambiar la descarga diaria de Garmin.'
    except (OSError, subprocess.TimeoutExpired):
        return 'No se ha podido cambiar la descarga diaria de Garmin.'
    return None


# ---------- Bicis del equipo de Garmin Connect ----------
_equipo = {}


def actualizar_equipo_garmin():
    """Lee de Garmin Connect las bicis y sus actividades. Devuelve None o el motivo del fallo."""
    if not usar_garmin():
        return 'La conexión con Garmin Connect está desactivada en Ajustes.'
    error, texto = _enviar_garmin('equipo', salida=True, manual=False)
    if error:
        return error
    try:
        datos = json.loads(texto.splitlines()[-1])
    except (ValueError, IndexError):
        return 'Garmin Connect ha devuelto una respuesta que no se entiende.'
    bicis.guardar_equipo_garmin(datos, datetime.now().isoformat(timespec='seconds'))
    return None


def equipo_en_segundo_plano(horas=20):
    """Una vez al día como mucho, al abrir Bicis: vuelve a leer el equipo de Garmin sin hacer esperar a la página."""
    if not usar_garmin() or not usuario_garmin() or not _python_garmindb():
        return
    hilo = _equipo.get('hilo')
    if hilo and hilo.is_alive():
        return
    f = bicis.equipo_garmin()['fecha']
    if f and (datetime.now() - datetime.fromisoformat(f)).total_seconds() < horas * 3600:
        return
    if _equipo.get('intento'):
        return  # una vez por sesión de VenB: con una contraseña mala no se insiste
    import threading
    _equipo['intento'] = datetime.now()
    _equipo['hilo'] = threading.Thread(target=actualizar_equipo_garmin, daemon=True)
    _equipo['hilo'].start()


def leyendo_equipo():
    h = _equipo.get('hilo')
    return bool(h and h.is_alive())


# ---------- Envíos a Garmin Connect ----------
def _python_garmindb():
    py = rutas.python_venv('garmindb')
    return py if os.path.exists(py) else None


def _enviar_garmin(*args, salida=False, manual=True):
    """Ejecuta garmin_enviar.py con el Python de garmindb. Devuelve None si Garmin lo acepta o el motivo del fallo.
    Con salida=True devuelve (error, lo que haya escrito). Cada llamada inicia sesión: pasa por el freno de
    garmin_freno (manual=True, los botones; False, lo que VenB hace sola)."""
    py = _python_garmindb()
    puede, motivo = FR.puede(manual) if py else (True, None)
    if not puede:
        error, texto = motivo, ''
    elif not py:
        error, texto = 'garmindb no está instalado en este ordenador.', ''
    else:
        entorno = dict(os.environ, PYTHONIOENCODING='utf-8')
        try:
            r = subprocess.run([py, os.path.join(AQUI, 'garmin_enviar.py'), *map(str, args)], capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=90, env=entorno)
            texto = (r.stdout or '').strip()
            error = ((r.stderr or '').strip().splitlines() or ['Error desconocido.'])[-1][:300] if r.returncode else None
        except (OSError, subprocess.TimeoutExpired):
            error, texto = 'Garmin Connect no responde. Inténtalo más tarde.', ''
        # una actividad que no existe no es un fallo de inicio de sesión
        if not error or 'no encuentra esa actividad' not in error:
            FR.registrar(not error, error or '')
    return (error, texto) if salida else error


# ---------- Cuenta de Garmin (garmindb) ----------
_descarga = {}


def usuario_garmin():
    """El usuario guardado en la configuración de garmindb, o ''. La contraseña nunca sale de ese fichero."""
    try:
        with open(_config_garmin(), encoding='utf-8') as f:
            return json.load(f)['credentials'].get('user') or ''
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return ''


def guardar_credenciales_garmin(usuario, clave):
    """Escribe usuario y contraseña donde garmindb los lee. Con la contraseña en blanco se conserva la anterior.
    Si cambian, se borra la sesión guardada para que el siguiente inicio de sesión use los datos nuevos."""
    if not _python_garmindb():
        raise ValueError('Antes hay que instalar la descarga automática: ejecuta de nuevo el instalador y responde «s».')
    ruta = _config_garmin()
    if os.path.exists(ruta):
        with open(ruta, encoding='utf-8') as f:
            config = json.load(f)
    else:
        with open(os.path.join(PROYECTO, 'config', 'GarminConnectConfig.json.plantilla'), encoding='utf-8') as f:
            config = json.load(f)
    cred = config.setdefault('credentials', {})
    if not clave and not cred.get('password'):
        raise ValueError('Escribe la contraseña de tu cuenta de Garmin.')
    cambia = cred.get('user') != usuario or bool(clave and clave != cred.get('password'))
    cred.update(user=usuario, secure_password=False, password_file=None, **({'password': clave} if clave else {}))
    os.makedirs(os.path.dirname(ruta), mode=0o700, exist_ok=True)
    with open(ruta + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
    try:
        os.chmod(ruta + '.tmp', 0o600)
    except OSError:
        pass
    os.replace(ruta + '.tmp', ruta)
    tokens = os.path.join(os.path.dirname(ruta), 'garmin_tokens.json')
    if cambia and os.path.exists(tokens):
        os.remove(tokens)
    if cambia:
        FR.nueva_clave()


def probar_garmin(manual=True):
    """(error, nombre de la cuenta)."""
    return _enviar_garmin('probar', salida=True, manual=manual)


def _log_descarga():
    return os.path.join(os.path.dirname(_config_garmin()), 'descarga_venb.log')


def descargar_todo():
    """Lanza en segundo plano la descarga completa de garmindb (la primera; luego basta la diaria). Devuelve el error o None."""
    if estado_descarga()['en_curso']:
        return 'Ya hay una descarga en curso.'
    py = _python_garmindb()
    if not py:
        return 'garmindb no está instalado en este ordenador.'
    puede, motivo = FR.puede(manual=True)
    if not puede:
        return motivo
    cli = os.path.join(os.path.dirname(py), 'garmindb_cli.py')
    log = open(_log_descarga(), 'w', encoding='utf-8')
    opciones = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    _descarga.update(proceso=subprocess.Popen([py, cli, '-f', rutas.GARMIN_CONFIG, '--all', '--download', '--import', '--analyze'], stdout=log, stderr=subprocess.STDOUT, cwd=rutas.GARMIN_CONFIG,
                                              stdin=subprocess.DEVNULL, env=dict(os.environ, PYTHONIOENCODING='utf-8'), **opciones),
                     inicio=datetime.now())
    log.close()
    return None


_reciente = {}


def _servicio_diario_activo():
    """La descarga diaria programada (Linux) está en marcha ahora: no se lanza otra a la vez."""
    if os.name == 'nt':
        return False
    try:
        return subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'garmindb.service'], timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def descargar_recientes(horas=3, forzar=False):
    """Trae lo nuevo de Garmin Connect en segundo plano (garmindb --latest, menos de un minuto): al arrancar VenB,
    cada `horas` mientras está abierta (al abrir Inicio) o con el botón de Inicio. Devuelve el motivo si no se lanza."""
    if not usar_garmin() or not usuario_garmin():
        return 'Garmin Connect no está configurado o está desactivado.'
    py = _python_garmindb()
    if not py:
        return 'garmindb no está instalado en este ordenador.'
    e = estado_recientes()
    if e['en_curso'] or estado_descarga()['en_curso']:
        return 'Ya hay una descarga en curso.'
    ultima = _reciente.get('inicio')
    if not forzar and ultima and (datetime.now() - ultima).total_seconds() < horas * 3600:
        return 'Descargado hace poco.'
    if _servicio_diario_activo():
        return 'La descarga diaria está en marcha.'
    # tras un fallo de inicio de sesión, esperas crecientes (también tras reabrir VenB); a mano, 3 intentos por hora
    puede, motivo = FR.puede(manual=forzar)
    if not puede:
        return motivo
    cli = os.path.join(os.path.dirname(py), 'garmindb_cli.py')
    log = open(_log_reciente(), 'w', encoding='utf-8')
    opciones = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    _reciente.pop('motivo', None)
    _reciente.update(proceso=subprocess.Popen([py, cli, '-f', rutas.GARMIN_CONFIG, '--all', '--download', '--import', '--analyze', '--latest'],
                                              stdout=log, stderr=subprocess.STDOUT, cwd=rutas.GARMIN_CONFIG, stdin=subprocess.DEVNULL,
                                              env=dict(os.environ, PYTHONIOENCODING='utf-8'), **opciones),
                     inicio=datetime.now())
    log.close()
    _reciente['antes'] = _n_actividades()
    return None


def _log_reciente():
    return os.path.join(os.path.dirname(_config_garmin()), 'descarga_reciente.log')


def _motivo_fallo(codigo):
    """garmindb termina bien aunque no pueda iniciar sesión: se mira su registro. Si ha fallado, se pregunta a Garmin
    Connect el motivo (contraseña, verificación en dos pasos, sin internet...). None si ha ido bien."""
    try:
        with open(_log_reciente(), encoding='utf-8', errors='replace') as f:
            texto = f.read()[-20000:]
    except OSError:
        texto = ''
    if codigo == 0 and not re.search(r'Failed to login|Traceback|ConnectionError|Max retries|HTTPError|\b429\b|\b1015\b|rate.?limit', texto, re.I):
        return None
    tipo = FR.clasificar(texto)
    if tipo == 'bloqueo':      # no se pregunta a Garmin otra vez: sería otro inicio de sesión
        return FR.MENSAJES['bloqueo']
    if FR.estado()['auto_hasta']:   # ya toca esperar: no se inicia sesión otra vez para saber el motivo
        FR.registrar(False, texto[-2000:])
        return FR.aviso()
    error, _ = probar_garmin(manual=False)  # pregunta el motivo; su resultado queda anotado en el freno
    return error or 'garmindb no ha podido completar la descarga (detalles en ' + _log_reciente() + ').'


def _n_actividades():
    return len(glob.glob(os.path.join(rutas.ruta_garmin(), 'activity_[0-9]*.json')))


def estado_recientes():
    """En curso, hora de inicio, resultado ('bien'/'mal') y actividades nuevas que ha traído."""
    p = _reciente.get('proceso')
    codigo = p.poll() if p else None
    hecho = bool(p) and codigo is not None
    if hecho and 'motivo' not in _reciente:
        _reciente['motivo'] = _motivo_fallo(codigo)
        if not _reciente['motivo']:
            FR.registrar(True)
        elif FR.clasificar(_reciente['motivo']) == 'bloqueo' and FR.estado()['tipo'] != 'bloqueo':
            FR.registrar(False, _reciente['motivo'])
    motivo = _reciente.get('motivo') if hecho else None
    return {'en_curso': bool(p) and codigo is None, 'inicio': _reciente.get('inicio'),
            'resultado': None if not hecho else ('mal' if motivo else 'bien'), 'motivo': motivo,
            'nuevas': max(_n_actividades() - _reciente.get('antes', 0), 0) if hecho else None}


def estado_descarga():
    """Estado de la descarga lanzada desde VenB mientras la app sigue abierta."""
    p = _descarga.get('proceso')
    if not p:
        return {'en_curso': False, 'inicio': None, 'resultado': None}
    codigo = p.poll()
    resultado = None
    if codigo is not None:
        resultado = 'bien' if codigo == 0 else 'mal'
    return {'en_curso': codigo is None, 'inicio': _descarga['inicio'], 'resultado': resultado, 'log': _log_descarga()}


def enviar_peso(fecha, kg):
    """Sube a Garmin Connect un peso anotado a mano, si el peso se toma de Garmin. Con la hora actual si es de hoy;
    si es de otro día, a las 12:00. Devuelve None si no hacía falta o ha ido bien, o el motivo del fallo."""
    if not peso_desde_garmin():
        return None
    f = date.fromisoformat(fecha)
    momento = datetime.now().replace(microsecond=0) if f == date.today() else datetime(f.year, f.month, f.day, 12)
    return _enviar_garmin('peso', momento.isoformat(), kg)


# ---------- Nombres de actividades ----------
def actividad(aid):
    """Fecha, tipo, título y km de una actividad del histórico; None si no existe."""
    d = historico()
    f = d[d.id.astype(str) == str(aid)] if not d.empty else d
    return None if f.empty else f.iloc[0].to_dict()


def _diezmar(filas, n=700):
    """Como mucho n puntos, repartidos a lo largo de la actividad."""
    if len(filas) <= n:
        return filas
    paso = (len(filas) - 1) / (n - 1)
    return [filas[round(i * paso)] for i in range(n)]


def track_actividad(aid):
    """[(km, altitud, lat, lon)] de una actividad: registros de garmindb, su FIT descargado o el fichero subido a mano.
    [] si no hay track (las del histórico exportado de Garmin no lo traen)."""
    import importar
    aid = str(aid)
    if importar.ES_ID.fullmatch(aid):
        return importar.puntos(aid)
    db = os.path.join(os.path.dirname(rutas.ruta_garmin_db()), 'garmin_activities.db')
    if os.path.exists(db):
        try:
            c = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=2)
            f = c.execute('select distance, altitude, position_lat, position_long from activity_records where activity_id=? order by record', (aid,)).fetchall()
            c.close()
            if f and any(x[0] for x in f):
                return f
        except sqlite3.Error:
            pass
    fit = os.path.join(rutas.ruta_garmin(), f'{aid}_ACTIVITY.fit')
    if os.path.exists(fit):
        try:
            return importar.leer_puntos(fit)
        except Exception:
            pass
    return []


def resumen_actividad(aid):
    """Datos principales y perfil de una actividad para la ventana de resumen del Histórico; None si no existe."""
    a = actividad(aid)
    if a is None:
        return None
    v = lambda x: None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)
    r = {'id': str(aid), 'titulo': a.get('titulo') or '', 'tipo': a.get('tipo') or '', 'fecha': f"{a['fecha']:%d/%m/%Y %H:%M}",
         'km': v(a.get('km')), 'h': v(a.get('h')), 'h_total': v(a.get('h_total')), 'desnivel': v(a.get('desnivel')), 'bici': bool(a.get('bici'))}
    try:
        df, _ = carga()
        f = df[df.id.astype(str).str.replace(r'\.0$', '', regex=True) == str(aid)]
        if len(f):
            x = f.iloc[0]
            r.update(fc_media=v(x['Frecuencia cardiaca media']), fc_max=v(x['FC máxima']), potencia_media=v(x['Potencia media']),
                     potencia_max=v(x['Potencia máxima']), np=v(x['Normalized Power® (NP®)']), p20=v(x['Potencia media máxima (20 minutos)']),
                     calorias=v(x['Calorías']), tss=v(x['tss']), tss_real=bool(x['tss_real']))
    except Exception:
        pass
    pts = _diezmar([p for p in track_actividad(aid) if p[0] is not None])
    r['perfil'] = [[round(p[0], 3), None if p[1] is None else round(p[1], 1)] for p in pts]
    r['track'] = [[round(p[2], 5), round(p[3], 5)] for p in pts if p[2] is not None and p[3] is not None]
    alt = [p[1] for p in r['perfil'] if p[1] is not None]
    r['alt_min'], r['alt_max'] = (min(alt), max(alt)) if alt else (None, None)
    try:      # validador de sensores: problemas y tramos sin datos (en km) para marcarlos sobre el perfil
        import sensores
        aj = rutas.ajustes()
        x = sensores.de_actividad(aid, a.get('tipo') in ('Ciclismo virtual', 'Ciclismo en sala'))
        pr = sensores.problemas(x, aj.get('sensores_vigilar', list(SENSORES)), aj.get('sensores_pct_aviso', 5))
        r['sensores'] = [t[0].upper() + t[1:] for _, t in pr]
        r['tramos_sensores'] = [[t[2], t[3], s] for s, d in (x or {}).get('sensores', {}).items() if s in dict(pr)
                                for t in d['tramos'] if t[2] is not None]
        r['potencia_dudosa'] = any(s == 'potencia' for s, _ in pr)
    except Exception:
        r['sensores'], r['tramos_sensores'], r['potencia_dudosa'] = [], [], False
    return r


def _renombrar_json(aid, nombre):
    ruta = os.path.join(rutas.ruta_garmin(), f'activity_{aid}.json')
    if not os.path.exists(ruta):
        return
    with open(ruta, encoding='utf-8') as f:
        a = json.load(f)
    a['activityName'] = nombre
    with open(ruta + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(a, f, ensure_ascii=False)
    os.replace(ruta + '.tmp', ruta)


def _renombrar_historico(aid, nombre):
    ruta = os.path.join(DATOS, 'historico_actividades.csv')
    if not os.path.exists(ruta):
        return
    with open(ruta, newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        campos, filas = r.fieldnames, list(r)
    if not any(x['id'] == str(aid) for x in filas):
        return
    for x in filas:
        if x['id'] == str(aid):
            x['titulo'] = nombre
    with open(ruta + '.tmp', 'w', newline='', encoding='utf-8') as f:
        e = csv.DictWriter(f, campos)
        e.writeheader()
        e.writerows(filas)
    os.replace(ruta + '.tmp', ruta)


def renombrar_actividad(aid, nombre):
    """Primero en Garmin Connect, con la sesión de garmindb; solo si Garmin lo acepta, también en las copias locales,
    para no esperar a la siguiente descarga. Las actividades subidas a mano, y todas si no se usa Garmin Connect,
    cambian solo en VenB. Devuelve None si ha ido bien o el motivo del fallo."""
    if importar.ES_ID.fullmatch(str(aid)):
        importar.renombrar(aid, nombre)
        _cache.clear()
        return None
    if usar_garmin():
        error = _enviar_garmin('nombre', aid, nombre)
        if error:
            return error
    _renombrar_json(aid, nombre)
    _renombrar_historico(aid, nombre)
    _cache.clear()
    return None


# ---------- Calendario ----------
def eventos_locales():
    if os.path.exists(EVENTOS):
        with open(EVENTOS, encoding='utf-8') as f:
            return json.load(f)
    return []


def _guardar_eventos(ev):
    tmp = EVENTOS + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(ev, f, ensure_ascii=False, indent=2)
    os.replace(tmp, EVENTOS)


def anadir_evento(fecha, nombre, notas=''):
    ev = eventos_locales()
    ev.append({'id': uuid.uuid4().hex, 'fecha': fecha, 'nombre': nombre, 'notas': notas})
    _guardar_eventos(ev)


def borrar_evento(eid):
    _guardar_eventos([e for e in eventos_locales() if e['id'] != eid])
    carpeta = carpeta_evento(eid)
    if os.path.isdir(carpeta):
        shutil.rmtree(carpeta)


# Calendarios: colores y nombres de cada origen (interruptores de la página Calendario)
ORIGENES = {'Randonneurs': ('#2e7d32', 'Randonneurs en España'), 'Mío': ('#1565c0', 'Mi Google Calendar'),
            'VenB': ('#c62828', 'Mi calendario de VenB'), 'Fecha clave': ('#ef6c00', 'Fechas clave')}
CAL_OCULTOS = os.path.join(DATOS, 'calendario_ocultos.json')


def evento_local(eid):
    return next((e for e in eventos_locales() if e['id'] == eid), None)


def carpeta_evento(eid):
    """Ficheros adjuntos de un evento de VenB (hoja de ruta y track): VenB-datos/calendario/<id>/."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', eid or ''):
        raise ValueError(eid)
    return os.path.join(rutas.PERSISTE, 'calendario', eid)


def editar_evento(eid, **cambios):
    ev = eventos_locales()
    for e in ev:
        if e['id'] == eid:
            e.update(cambios)
            _guardar_eventos(ev)
            return e
    raise KeyError(eid)


def copiar_evento(uid, fecha, nombre, notas='', origen=''):
    """Copia un evento de un calendario externo al de VenB (una sola vez). Devuelve su id."""
    ev = eventos_locales()
    ya = next((e for e in ev if uid and e.get('origen_uid') == uid), None)
    if ya:
        return ya['id']
    nuevo = {'id': uuid.uuid4().hex, 'fecha': fecha, 'nombre': nombre, 'notas': notas, 'origen_uid': uid, 'copiado_de': origen}
    _guardar_eventos(ev + [nuevo])
    return nuevo['id']


def ocultos():
    """Eventos sueltos de los calendarios externos que no se quieren ver: [{uid, nombre, fecha, origen}]."""
    try:
        with open(CAL_OCULTOS, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _guardar_ocultos(filas):
    with open(CAL_OCULTOS + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(filas, f, ensure_ascii=False, indent=1)
    os.replace(CAL_OCULTOS + '.tmp', CAL_OCULTOS)


def ocultar_evento(uid, nombre, fecha, origen):
    if uid and uid not in {o['uid'] for o in ocultos()}:
        _guardar_ocultos(ocultos() + [{'uid': uid, 'nombre': nombre, 'fecha': fecha, 'origen': origen}])


def mostrar_evento(uid):
    _guardar_ocultos([o for o in ocultos() if o['uid'] != uid])


def calendarios_ocultos():
    """Orígenes ocultos con los interruptores de la página Calendario (el de Randonneurs, con calendario_defecto_ver)."""
    a = rutas.ajustes()
    return set(a.get('calendarios_ocultos', [])) | (set() if a.get('calendario_defecto_ver', True) else {'Randonneurs'})


def ver_calendario(origen, ver):
    if origen not in ORIGENES:
        raise ValueError(origen)
    if origen == 'Randonneurs':
        rutas.guardar_ajustes({'calendario_defecto_ver': bool(ver)})
        return
    ocultos_ = set(rutas.ajustes().get('calendarios_ocultos', []))
    ocultos_ = ocultos_ - {origen} if ver else ocultos_ | {origen}
    rutas.guardar_ajustes({'calendarios_ocultos': sorted(ocultos_)})


def exportar_ics():
    """El calendario de VenB en formato iCal, para importarlo o suscribirse desde el móvil."""
    def txt(v):
        return str(v or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')
    lineas = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//VenB//Calendario//ES', 'CALSCALE:GREGORIAN', 'X-WR-CALNAME:VenB']
    sello = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for e in eventos_locales():
        d = date.fromisoformat(e['fecha'])
        lineas += ['BEGIN:VEVENT', f"UID:{e['id']}@venb", f'DTSTAMP:{sello}', f'DTSTART;VALUE=DATE:{d:%Y%m%d}',
                   f'DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}', f"SUMMARY:{txt(e['nombre'])}"]
        if e.get('notas'):
            lineas.append(f"DESCRIPTION:{txt(e['notas'])}")
        lineas.append('END:VEVENT')
    return '\r\n'.join(lineas + ['END:VCALENDAR']) + '\r\n'


def fechas_clave():
    if not os.path.exists(rutas.AVISOS):
        return []
    with open(rutas.AVISOS, encoding='utf-8') as f:
        filas = json.load(f)
    for a in filas:  # las escritas a mano pueden no llevar identificador
        a.setdefault('id', hashlib.sha1(f"{a['fecha']}{a['texto']}".encode()).hexdigest()[:16])
    return filas


def _guardar_fechas_clave(filas):
    with open(rutas.AVISOS + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(filas, f, ensure_ascii=False, indent=1)
    os.replace(rutas.AVISOS + '.tmp', rutas.AVISOS)


def anadir_fecha_clave(fecha, texto, dias_antes=14):
    _guardar_fechas_clave(fechas_clave() + [{'id': uuid.uuid4().hex[:16], 'fecha': fecha, 'dias_antes': dias_antes, 'texto': texto}])


def borrar_fecha_clave(fid):
    _guardar_fechas_clave([a for a in fechas_clave() if a['id'] != fid])


def guardar_calendario(url):
    """Guarda o, sin dirección, quita el calendario propio. Su copia local deja de valer en ambos casos."""
    if os.path.exists(CAL_CACHE_PROPIO):
        os.remove(CAL_CACHE_PROPIO)
    if not url:
        if os.path.exists(CAL_URL):
            os.remove(CAL_URL)
        return
    with open(CAL_URL, 'w', encoding='utf-8') as f:
        f.write(url + '\n')
    try:
        os.chmod(CAL_URL, 0o600)
    except OSError:
        pass


def _leer_ics(texto):
    """Lector mínimo de iCal: fecha, resumen y lugar. No expande eventos repetidos."""
    texto = re.sub(r'\r?\n[ \t]', '', texto)
    limpia = lambda v: v.replace('\\n', ' ').replace('\\,', ',').replace('\\;', ';').replace('\\\\', '\\')
    salida, ev = [], None
    for linea in texto.splitlines():
        if linea == 'BEGIN:VEVENT':
            ev = {}
        elif linea == 'END:VEVENT':
            if ev and ev.get('fecha') and ev.get('estado') != 'CANCELLED':
                salida.append(ev)
            ev = None
        elif ev is not None and ':' in linea:
            k, v = linea.split(':', 1)
            k = k.split(';')[0]
            if k == 'DTSTART':
                try:
                    if v.endswith('Z'):
                        ev['fecha'] = datetime.strptime(v, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).astimezone().date()
                    else:
                        ev['fecha'] = datetime.strptime(v[:8], '%Y%m%d').date()
                except ValueError:
                    pass
            elif k == 'UID':
                ev['uid'] = v.strip()
            elif k == 'SUMMARY':
                ev['nombre'] = limpia(v)
            elif k == 'LOCATION':
                ev['notas'] = limpia(v)
            elif k == 'STATUS':
                ev['estado'] = v
            elif k == 'RRULE':
                ev['repite'] = True
    return salida


def calendario_propio():
    return os.path.exists(CAL_URL)


def calendarios():
    """[(dirección, nombre, etiqueta, caché, propio)]: el de Randonneurs (si no se ha ocultado) y, además, el propio."""
    a = rutas.ajustes()
    salida = []
    if a.get('calendario_defecto') and a.get('calendario_defecto_ver', True):
        salida.append((a['calendario_defecto'], a.get('calendario_defecto_nombre', 'Calendario'), 'Randonneurs', CAL_CACHE, False))
    if calendario_propio():
        with open(CAL_URL, encoding='utf-8') as f:
            salida.append((f.read().strip(), 'tu calendario', 'Mío', CAL_CACHE_PROPIO, True))
    return salida


def _eventos_ics(url, nombre, cache, propio):
    """Devuelve (eventos, error). Refresca como mucho cada 3 horas y usa la última copia si falla."""
    error = None
    if not os.path.exists(cache) or time.time() - os.path.getmtime(cache) > 3 * 3600:
        try:
            if not url.startswith('https://'):
                raise ValueError
            with urllib.request.urlopen(url, timeout=10) as r:
                texto = r.read(20_000_000).decode('utf-8', 'replace')
            if 'BEGIN:VCALENDAR' not in texto:
                raise ValueError
            with open(cache, 'w', encoding='utf-8') as f:
                f.write(texto)
        except Exception:
            if os.path.exists(cache):
                error = f'No se ha podido actualizar {nombre if propio else "«" + nombre + "»"}; se muestra la última copia.'
            elif propio:
                error = 'No se ha podido leer tu calendario. Comprueba que has copiado la «Dirección secreta en formato iCal», que termina en .ics, y que tienes conexión.'
            else:
                error = f'No se ha podido leer el calendario «{nombre}». Comprueba la conexión.'
    if not os.path.exists(cache):
        return [], error
    with open(cache, encoding='utf-8') as f:
        return _leer_ics(f.read()), error


def proximos_eventos(meses=12):
    """(lista de meses con sus eventos, errores de los calendarios unidos en un texto). Los eventos externos ocultos
    uno a uno no salen; los copiados al calendario de VenB llevan 'copiado'."""
    hoy = date.today()
    locales = eventos_locales()
    todos = [{**e, 'fecha': date.fromisoformat(e['fecha']), 'origen': 'VenB'} for e in locales]
    copiados = {e.get('origen_uid') for e in locales if e.get('origen_uid')}
    no_ver = {o['uid'] for o in ocultos()}
    errores = []
    for url, nombre, etiqueta, cache, propio in calendarios():
        evs, error = _eventos_ics(url, nombre, cache, propio)
        todos += [{**e, 'origen': etiqueta, 'nombre': e.get('nombre', '(sin título)'), 'copiado': e.get('uid') in copiados}
                  for e in evs if not e.get('uid') or e['uid'] not in no_ver]
        if error:
            errores.append(error)
    todos += [{'fecha': date.fromisoformat(a['fecha']), 'nombre': a['texto'][0].upper() + a['texto'][1:], 'origen': 'Fecha clave', 'id': a['id']} for a in fechas_clave()]
    salida, a, m = [], hoy.year, hoy.month
    for _ in range(meses):
        ev = sorted((e for e in todos if e['fecha'].year == a and e['fecha'].month == m and e['fecha'] >= hoy), key=lambda e: e['fecha'])
        salida.append({'nombre': f'{MES[m - 1]} {a}', 'eventos': ev})
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return salida, ' '.join(errores) or None


# ---------- Informes y consejos ----------
def informes():
    salida = []
    for d in sorted(glob.glob(os.path.join(INFORMES, '*')), reverse=True):
        if os.path.isdir(d):
            nombres = sorted(os.listdir(d))
            salida.append({'carpeta': os.path.basename(d), 'pdf': [n for n in nombres if n.endswith('.pdf')], 'svg': [n for n in nombres if n.endswith('.svg')]})
    return salida


def estados():
    salida = []
    for f in sorted(glob.glob(os.path.join(ESTADO, 'estado_*.md')), reverse=True):
        with open(f, encoding='utf-8') as fh:
            lineas = fh.read().splitlines()
        salida.append({'titulo': lineas[0].lstrip('# ') if lineas else os.path.basename(f), 'puntos': [l[2:] for l in lineas[1:] if l.startswith('- ')]})
    return salida


def ultimo_consejo():
    for d in sorted(glob.glob(os.path.join(INFORMES, '*')), reverse=True):
        ruta = os.path.join(d, 'notas.json')
        if os.path.exists(ruta):
            with open(ruta, encoding='utf-8') as f:
                return {**json.load(f), 'carpeta': os.path.basename(d)}
    return None


# ---------- Cortes de potencia ----------
def cortes_recientes(n=3):
    """Porcentaje de tiempo a 0 W (cortes de 3 s o más) en las últimas sesiones de rodillo. Con caché."""
    try:
        from fitparse import FitFile
    except ImportError:
        return []
    try:
        df, _ = carga()
    except Exception:
        return []
    rut = os.path.join(DATOS, 'cortes_cache.json')
    cache = json.load(open(rut, encoding='utf-8')) if os.path.exists(rut) else {}
    salida = []
    for _, a in df[df.virtual].sort_values('Fecha').tail(n).iterrows():
        aid = str(a.id)
        if aid not in cache:
            fit = glob.glob(os.path.join(rutas.ruta_garmin(), f'{aid}*.fit'))
            if not fit:
                continue
            try:
                p = pd.Series([m.get_value('power') for m in FitFile(fit[0]).get_messages('record')], dtype=float)
                cero = (p == 0) | p.isna()
                g = cero.groupby((cero != cero.shift()).cumsum()).sum()
                cache[aid] = round(100 * g[g >= 3].sum() / max(len(p), 1), 1)
            except Exception:
                continue
        salida.append({'id': aid, 'fecha': a.Fecha.date(), 'titulo': a['Título'], 'pct': cache[aid]})
    tmp = rut + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cache, f)
    os.replace(tmp, rut)
    return salida


# Sensores que vigila el validador de sesiones (Ajustes > Sensores)
SENSORES = {'fc': 'Pulsómetro', 'potencia': 'Potencia', 'cadencia': 'Cadencia', 'velocidad': 'Velocidad y distancia', 'gps': 'GPS (en exterior)'}


# ---------- Avisos ----------
AVISOS_CERRADOS = os.path.join(DATOS, 'avisos_cerrados.json')


def avisos_cerrados():
    try:
        with open(AVISOS_CERRADOS, encoding='utf-8') as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def cerrar_aviso(clave):
    """Cada aviso tiene una clave con su fecha o su mes: cerrar uno no oculta los siguientes del mismo tipo."""
    c = sorted(avisos_cerrados() | {clave[:120]})
    with open(AVISOS_CERRADOS + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
    os.replace(AVISOS_CERRADOS + '.tmp', AVISOS_CERRADOS)


def avisos():
    """Lo que hay que atender ahora: datos atrasados, fechas clave, cierre mensual y sesiones con cortes.
    Se omiten los que se han cerrado con su X."""
    hoy, r = date.today(), []
    a = rutas.ajustes()
    cerrados = avisos_cerrados()
    def aviso(nivel, texto, accion='', clave='', enlace=None):
        if clave not in cerrados:
            r.append({'nivel': nivel, 'texto': texto, 'accion': accion, 'clave': clave, 'enlace': enlace})
    if not usar_garmin():
        if historico().empty:
            aviso('bajo', 'Todavía no hay actividades.', 'Súbelas en Análisis > Importar.', 'sin_actividades', ('Importar actividades', '/importar'))
    elif glob.glob(os.path.join(rutas.ruta_garmin(), 'activity_[0-9]*.json')):
        try:
            df, _ = carga()
            ultima = df.Fecha.max().date()
            d = (hoy - ultima).days
            if d > a['dias_sin_actividad']:
                aviso('alto', f'La última actividad registrada es de hace {d} días ({ultima:%d/%m/%Y}).', 'Si has rodado, comprueba la descarga de Garmin.', f'actividad:{ultima}')
        except Exception:
            aviso('alto', 'No se han podido leer las actividades de Garmin.', 'Comprueba la descarga de Garmin.', f'lectura:{hoy}')
        s = salud()
        if s is None or not s['ultimo']:
            aviso('medio', 'No se han podido leer los datos de sueño y VFC.', 'Puede ser temporal si hay una descarga en marcha.', f'salud:{hoy}')
        elif (hoy - s['ultimo']).days > a['dias_sin_salud']:
            aviso('medio', f"Los datos de salud llegan solo hasta el {s['ultimo']:%d/%m/%Y}.", 'Comprueba que el reloj se ha sincronizado con Garmin Connect.', f"salud:{s['ultimo']}")
    else:
        if historico().empty:
            aviso('bajo', 'Todavía no hay actividades.', 'Consulta en Ayuda cómo incorporar tus datos de Garmin o súbelas en Análisis > Importar.', 'sin_garmin', ('Importar actividades', '/importar'))
    p = pesos()
    if p and (hoy - date.fromisoformat(p[-1][0])).days > a['dias_sin_peso']:
        aviso('bajo', f'El último peso anotado es del {date.fromisoformat(p[-1][0]):%d/%m/%Y}.', 'Comprueba que llega a Garmin Connect o anótalo en esta página.' if peso_desde_garmin() else 'Anótalo en esta página.', f'peso:{p[-1][0]}')
    for f in fechas_clave():
        falta = (date.fromisoformat(f['fecha']) - hoy).days
        if 0 <= falta <= f.get('dias_antes', 14):
            aviso('medio', f"{date.fromisoformat(f['fecha']):%d/%m/%Y}: {f['texto']}.", 'Hoy.' if falta == 0 else f'Faltan {falta} días.', f"fecha:{f.get('id', '')}:{f['fecha']}")
    pend = bicis.pendiente()
    if pend:
        aviso('medio', f"Cierra {MES[int(pend[5:7]) - 1]} de {pend[:4]}: anota los kilómetros de cada bici y si hubo alguna reparación.", 'En la página Bicis.',
              f'cierre:{pend}', ('Ir al cierre del mes', f'/bicis?mes={pend[5:7]}/{pend[:4]}#mes'))
    try:
        import brevets
        if usar_garmin() and FR.aviso():
            fr = FR.estado()
            aviso('alto', 'Garmin Connect: ' + FR.aviso(), 'Más información en Ayuda > Importar tus datos de Garmin.',
                  f"garmin-freno:{fr['ultimo']:%Y-%m-%dT%H:%M}" if fr['ultimo'] else 'garmin-freno', ('Ver la ayuda', '/ayuda/garmin#si-garmin-bloquea-el-acceso'))
        km_min = a.get('km_aviso_prueba', 190)
        recientes = brevets.sin_registrar(historico(), km_min, a.get('dias_aviso_prueba', 60), hoy)
        for s in recientes:
            km = f'{s.km:.0f}'
            aviso('medio', f"Salida de {km} km el {s.fecha:%d/%m/%Y}{' («' + s.titulo + '»)' if s.titulo else ''}. ¿Fue una prueba oficial: brevet, superbrevet, flecha o Super Randonnée?",
                  'Si fue una salida sin más, ciérralo con la ×.', f'prueba:{s.id}', ('Sí, registrarla', f'/brevets?actividad={s.id}#formulario'))
        # las anteriores (p. ej., importadas de golpe), en un solo aviso; vuelve a salir si aumentan
        n = len(brevets.sin_registrar(historico(), km_min))
        if n > len(recientes):
            aviso('bajo', f"Tienes {n} salidas de {km_min} km o más sin clasificar: ¿alguna fue una prueba oficial?",
                  'Puedes marcarlas todas como «No es prueba» de una vez.', f'por-clasificar:{n}', ('Clasificarlas', '/brevets/por-clasificar'))
    except Exception:
        pass
    # validador de sensores: con lo que ya está analizado; lo nuevo se analiza en segundo plano
    try:
        import sensores
        df, _ = carga()
        args = (df, a.get('sensores_dias_aviso', 7), a.get('sensores_vigilar', list(SENSORES)), a.get('sensores_pct_aviso', 5))
        for s in sensores.revisar(*args, calcular=False):
            textos = '; '.join(t for _, t in s['problemas'])
            aviso('medio', f"Sesión del {s['fecha']:%d/%m/%Y}{' («' + s['titulo'] + '»)' if s['titulo'] else ''}: {textos[0].upper() + textos[1:]}.",
                  'Su potencia y su TSS pueden no ser fiables.' if any(x == 'potencia' for x, _ in s['problemas'])
                  else 'Revisa el sensor (batería, emparejamiento) antes de la próxima salida.', f"sensores:{s['id']}",
                  ('Ver la sesión', f"/historico?q=&resumen={s['id']}"))
        sensores.revisar_en_segundo_plano(*args)
    except Exception:
        pass
    return r
