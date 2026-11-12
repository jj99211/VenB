"""Bicicletas de VenB: alta de bicis, kilómetros por mes, piezas cambiadas y visitas al mecánico.
Se guarda en VenB-datos/datos/bicis/. También se puede anotar desde la terminal:
  python venb/bicis.py km --mes 11/2026 --bici mi-bici --km 150
  python venb/bicis.py km --mes 11/2026 --bici mi-bici --juego gravel --km 20
  python venb/bicis.py pieza --fecha 02/11/2026 --bici mi-bici --pieza Cadena --visita mecanico --taller "X" --coste 30
  python venb/bicis.py cierre --mes 11/2026
VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0."""
import argparse
import calendar
import csv
import json
import os
import re
import sys
import unicodedata
import uuid
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import rutas  # noqa: E402

DIR = os.path.join(rutas.DATOS, 'bicis')
BICIS = os.path.join(DIR, 'bicis.json')
KM = os.path.join(DIR, 'km.csv')
PIEZAS = os.path.join(DIR, 'piezas.csv')
CIERRES = os.path.join(DIR, 'cierres.json')
ASIGNACIONES = os.path.join(DIR, 'actividades.csv')   # bici de cada actividad (opcional)
CAMPOS_ASIG = ['actividad', 'bici', 'rodadura']
EQUIPO = os.path.join(DIR, 'garmin_equipo.json')    # bicis de Garmin Connect, sus actividades y a qué bici de VenB corresponden
OTRA = 'otra'   # BiciMAD, alquilada, prestada...: cuenta como entrenamiento, no en los km de tus bicis
CAMPOS_KM = ['mes', 'bici', 'rodadura', 'km']
CAMPOS_PIEZA = ['id', 'fecha', 'aprox', 'bici', 'pieza', 'visita', 'taller', 'coste', 'km_cambio', 'origen', 'notas']
VISITAS = {'mecanico': 'Mecánico', 'propia': 'Yo mismo', '': 'Sin indicar'}
MAX_SERIES = 8  # más colores no se distinguen: el resto se agrupa en «Otras»
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']


def _csv(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _guardar_csv(ruta, campos, filas):
    os.makedirs(DIR, exist_ok=True)
    tmp = ruta + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        e = csv.DictWriter(f, campos)
        e.writeheader()
        e.writerows(filas)
    os.replace(tmp, ruta)


def _mes_actual(hoy=None):
    hoy = hoy or date.today()
    return f'{hoy.year}-{hoy.month:02d}'


# ---------- Catálogo de bicis ----------
def cargar_bicis():
    if not os.path.exists(BICIS):
        return []
    with open(BICIS, encoding='utf-8') as f:
        return [{'activa': True, 'juegos': [], 'componentes': [], 'km_base': 0, 'serie': '', 'platos': [], 'pinones': [], **b} for b in json.load(f)]


def activas():
    return [b for b in cargar_bicis() if b['activa']]


def una_bici(bid):
    return next((b for b in cargar_bicis() if b['id'] == bid), None)


def _guardar_bicis(bs):
    os.makedirs(DIR, exist_ok=True)
    with open(BICIS + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(bs, f, ensure_ascii=False, indent=1)
    os.replace(BICIS + '.tmp', BICIS)


def _identificador(nombre, usados):
    base = unicodedata.normalize('NFKD', nombre).encode('ascii', 'ignore').decode().lower()
    base = re.sub(r'[^a-z0-9]+', '-', base).strip('-') or 'bici'
    bid, n = base, 2
    while bid in usados:
        bid, n = f'{base}-{n}', n + 1
    return bid


def _componente(nombre, base, mes_base, rodadura=''):
    return {'nombre': nombre, 'base': base, 'mes_base': mes_base, 'rodadura': rodadura}


def _piezas_con_juegos(piezas, juegos):
    """Con varios juegos de ruedas, cada uno lleva sus cubiertas y solo suma sus kilómetros."""
    salida = []
    for p in piezas:
        if p == 'Cubiertas' and juegos:
            salida += [(f'Cubiertas {j}', j) for j in juegos]
        else:
            salida.append((p, ''))
    return salida


def crear_bici(nombre, km_base=0, serie='', juegos=(), piezas=(), platos=(), pinones=()):
    bs = cargar_bicis()
    bid = _identificador(nombre, {b['id'] for b in bs})
    juegos = list(juegos)
    comps = [_componente(n, km_base, '', r) for n, r in _piezas_con_juegos(piezas, juegos)]
    bs.append({'id': bid, 'nombre': nombre, 'km_base': km_base, 'activa': True, 'serie': serie, 'juegos': juegos, 'platos': list(platos), 'pinones': list(pinones), 'componentes': comps})
    _guardar_bicis(bs)
    if not rutas.ajustes().get('primer_mes_cierre'):
        rutas.guardar_ajustes({'primer_mes_cierre': _mes_actual()})
    return bid


def editar_bici(bid, nombre, km_base, serie, activa, juegos, piezas, platos, pinones):
    """Conserva los contadores de lo que ya existía. Lo nuevo cuenta desde este mes."""
    bs = cargar_bicis()
    b = next(x for x in bs if x['id'] == bid)
    juegos = list(dict.fromkeys(list(b['juegos']) + list(juegos)))  # un juego con km no se puede quitar
    viejas = {c['nombre']: c for c in b['componentes']}
    comps = []
    for n, r in _piezas_con_juegos(piezas, juegos):
        comps.append(viejas.get(n) or _componente(n, 0, _mes_actual(), r))
    b.update(nombre=nombre, km_base=km_base, serie=serie, activa=activa, juegos=juegos, componentes=comps, platos=list(platos), pinones=list(pinones))
    _guardar_bicis(bs)


def borrar_bici(bid):
    """Solo sin historial: una bici con datos se descataloga, no se borra."""
    if any(r['bici'] == bid for r in _csv(KM)) or any(p['bici'] == bid for p in _csv(PIEZAS)) or bid in {a[0] for a in asignaciones().values()}:
        raise ValueError('La bici tiene historial')
    _guardar_bicis([b for b in cargar_bicis() if b['id'] != bid])


# ---------- Kilómetros y piezas ----------
def km_filas():
    return [{**r, 'km': float(r['km'])} for r in _csv(KM)]


def piezas():
    return sorted(_csv(PIEZAS), key=lambda p: p['fecha'], reverse=True)


def anotar_km(mes, bici, km, rodadura=''):
    """Sustituye el dato de ese mes: volver a anotarlo lo corrige, no lo suma."""
    filas = [r for r in _csv(KM) if not (r['mes'] == mes and r['bici'] == bici and r['rodadura'] == rodadura)]
    filas.append({'mes': mes, 'bici': bici, 'rodadura': rodadura, 'km': km})
    _guardar_csv(KM, CAMPOS_KM, sorted(filas, key=lambda r: (r['mes'], r['bici'])))


def borrar_km(mes, bici, rodadura=''):
    _guardar_csv(KM, CAMPOS_KM, [r for r in _csv(KM) if not (r['mes'] == mes and r['bici'] == bici and r['rodadura'] == rodadura)])


def anotar_pieza(fecha, bici, pieza, visita='', taller='', coste='', notas=''):
    filas = _csv(PIEZAS)
    filas.append({'id': uuid.uuid4().hex, 'fecha': fecha, 'aprox': '', 'bici': bici, 'pieza': pieza, 'visita': visita, 'taller': taller,
                  'coste': coste, 'km_cambio': '', 'origen': 'app', 'notas': notas})
    _guardar_csv(PIEZAS, CAMPOS_PIEZA, filas)


def una_pieza(pid):
    return next((p for p in _csv(PIEZAS) if p['id'] == pid), None)


def editar_pieza(pid, **campos):
    """Una fecha corregida a mano deja de ser aproximada."""
    filas = _csv(PIEZAS)
    for p in filas:
        if p['id'] == pid:
            if campos.get('fecha') != p['fecha']:
                p['aprox'] = ''
            p.update(campos)
    _guardar_csv(PIEZAS, CAMPOS_PIEZA, filas)


def borrar_pieza(pid):
    _guardar_csv(PIEZAS, CAMPOS_PIEZA, [p for p in _csv(PIEZAS) if p['id'] != pid])


# ---------- Bici de cada actividad ----------
def asignaciones(con_origen=False):
    """{id de actividad: (bici, rodadura)}; bici puede ser OTRA. La elegida en VenB manda sobre la de Garmin Connect,
    que se toma de la bici de Garmin según su correspondencia (si no tiene, la actividad queda sin asignar).
    Con con_origen=True, {id: ((bici, rodadura), 'venb' | 'garmin')}."""
    e = equipo_garmin()
    corr, salida = e['correspondencia'], {}
    # Garmin pone en el rodillo su bici por defecto: si así se elige en Ajustes, ahí manda la bici del rodillo
    a = rutas.ajustes()
    saltar = set(e['rodillo']) if a.get('rodillo_manda', True) and a.get('bici_rodillo') else set()
    for aid, gid in e['actividades'].items():
        v = corr.get(gid)
        if v and aid not in saltar:
            salida[aid] = (tuple(v.split('|', 1)), 'garmin')
    for r in _csv(ASIGNACIONES):
        salida[r['actividad']] = ((r['bici'], r['rodadura']), 'venb')
    return salida if con_origen else {k: v for k, (v, _) in salida.items()}


def equipo_garmin():
    """{'fecha': última lectura, 'bicis': [{uuid, nombre, modelo, retirada, n}], 'actividades': {id: uuid},
    'correspondencia': {uuid: «bici|juego» de opciones_bici() o ''}}."""
    try:
        with open(EQUIPO, encoding='utf-8') as f:
            e = json.load(f)
    except (OSError, ValueError):
        e = {}
    return {'fecha': e.get('fecha'), 'bicis': e.get('bicis', []), 'actividades': e.get('actividades', {}), 'rodillo': e.get('rodillo', []),
            'correspondencia': e.get('correspondencia', {})}


def _guardar_equipo(e):
    os.makedirs(DIR, exist_ok=True)
    with open(EQUIPO + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(e, f, ensure_ascii=False)
    os.replace(EQUIPO + '.tmp', EQUIPO)


def _palabras(t):
    t = unicodedata.normalize('NFKD', t or '').encode('ascii', 'ignore').decode().lower()
    return {w for w in re.findall(r'[a-z0-9]+', t) if len(w) >= 3 or w.isdigit()}


def _sugerir(gb, valores):
    """Bici de VenB con el nombre más parecido a una de Garmin (al menos una palabra en común y sin empate).
    Solo bicis sin juegos de ruedas: en las que tienen varios, el juego lo elige el usuario."""
    g = _palabras(gb['nombre'] + ' ' + gb.get('modelo', ''))
    notas = []
    for b in cargar_bicis():
        if b['juegos'] and b['activa']:
            continue
        n = len(g & _palabras(b['nombre'] + ' ' + b.get('serie', '')))
        if n:
            notas.append((n, f"{b['id']}|"))
    notas.sort(reverse=True)
    if notas and (len(notas) == 1 or notas[0][0] > notas[1][0]) and notas[0][1] in valores:
        return notas[0][1]
    return ''


def guardar_equipo_garmin(bicis_garmin, fecha):
    """Guarda lo leído de Garmin Connect; conserva las correspondencias y propone las de las bicis nuevas."""
    e = equipo_garmin()
    valores = {o['valor'] for o in opciones_bici()}
    corr = e['correspondencia']
    for gb in bicis_garmin:
        if gb['uuid'] not in corr:
            corr[gb['uuid']] = _sugerir(gb, valores)
    act = {}
    for gb in bicis_garmin:
        for aid in gb['actividades']:
            act.setdefault(aid, gb['uuid'])
    rodillo = sorted({aid for gb in bicis_garmin for aid in gb.get('rodillo', [])})
    _guardar_equipo({'fecha': fecha, 'correspondencia': corr, 'actividades': act, 'rodillo': rodillo,
                     'bicis': [{k: gb.get(k) for k in ('uuid', 'nombre', 'modelo', 'retirada')} | {'n': len(gb['actividades'])} for gb in bicis_garmin]})


def corresponder(cambios):
    """cambios: {uuid: «bici|juego» o ''}."""
    e = equipo_garmin()
    valores = {o['valor'] for o in opciones_bici()} | {''}
    for gid, v in cambios.items():
        if gid in {b['uuid'] for b in e['bicis']} and v in valores:
            e['correspondencia'][gid] = v
    _guardar_equipo(e)


def opciones_bici():
    """Valores del desplegable «bici|juego» con su texto: bicis en uso (una por juego), retiradas y «Otra»."""
    salida = []
    for b in sorted(cargar_bicis(), key=lambda b: not b['activa']):
        sufijo = '' if b['activa'] else ' (retirada)'
        for j in (b['juegos'] if b['activa'] and b['juegos'] else ['']):
            salida.append({'valor': f"{b['id']}|{j}", 'texto': f"{b['nombre']}{', ' + j if j else ''}{sufijo}"})
    salida.append({'valor': f'{OTRA}|', 'texto': 'Otra (no mía)'})
    return salida


def asignar(actividad, valor):
    """valor: «bici|juego» de opciones_bici(), o vacío para quitar la asignación."""
    if valor and valor not in {o['valor'] for o in opciones_bici()}:
        raise ValueError('Bici desconocida')
    filas = [r for r in _csv(ASIGNACIONES) if r['actividad'] != actividad]
    if valor:
        bici, rod = valor.split('|', 1)
        filas.append({'actividad': actividad, 'bici': bici, 'rodadura': rod})
    _guardar_csv(ASIGNACIONES, CAMPOS_ASIG, filas)


# ---------- Cierre mensual ----------
def cierres():
    if not os.path.exists(CIERRES):
        return []
    with open(CIERRES, encoding='utf-8') as f:
        return json.load(f)


def cerrar_mes(mes):
    c = sorted(set(cierres()) | {mes})
    os.makedirs(DIR, exist_ok=True)
    with open(CIERRES + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(c, f)
    os.replace(CIERRES + '.tmp', CIERRES)


def mes_a_preguntar(hoy=None):
    """Ventana de cierre configurable, por defecto del día 28 al 7 del mes siguiente. Fuera de ella, None."""
    hoy = hoy or date.today()
    a = rutas.ajustes()
    if hoy.day >= a['cierre_dia_inicio']:
        return _mes_actual(hoy)
    if hoy.day <= a['cierre_dia_fin']:
        an, m = (hoy.year - 1, 12) if hoy.month == 1 else (hoy.year, hoy.month - 1)
        return f'{an}-{m:02d}'
    return None


def _primer_mes():
    return rutas.ajustes().get('primer_mes_cierre') or ''


def pendiente(hoy=None):
    mes, primero = mes_a_preguntar(hoy), _primer_mes()
    return mes if mes and primero and activas() and mes >= primero and mes not in cierres() else None


def sin_cerrar(hoy=None):
    """Meses terminados sin cerrar, salvo el de la ventana actual."""
    hoy = hoy or date.today()
    primero = _primer_mes()
    if not primero or not activas():
        return []
    salida, a, m = [], int(primero[:4]), int(primero[5:7])
    hechos, ventana = set(cierres()), mes_a_preguntar(hoy)
    while (a, m) < (hoy.year, hoy.month):
        mes = f'{a}-{m:02d}'
        if mes not in hechos and mes != ventana:
            salida.append(mes)
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return salida


def admite_cierre(mes, hoy=None):
    """El mes en curso no se da por cerrado antes de que empiece la ventana."""
    hoy = hoy or date.today()
    actual = _mes_actual(hoy)
    return mes < actual or (mes == actual and hoy.day >= rutas.ajustes()['cierre_dia_inicio'])


# ---------- Temporadas y resúmenes ----------
def temporada(mes):
    """Una temporada lleva el año en que termina. Si empieza en enero, es el año natural."""
    inicio = rutas.ajustes()['mes_inicio_temporada']
    a, m = int(mes[:4]), int(mes[5:7])
    return a + 1 if inicio > 1 and m >= inicio else a


def etiqueta_temporada(t):
    return str(t) if rutas.ajustes()['mes_inicio_temporada'] == 1 else f'{str(t - 1)[2:]}-{str(t)[2:]}'


def descripcion_temporada():
    i = rutas.ajustes()['mes_inicio_temporada']
    return 'Por año natural.' if i == 1 else f'De {MESES[i - 1]} a {MESES[i - 2]}.'


def _km_comp(bici, comp, filas, eventos):
    """Km de una pieza desde su último cambio. Un cambio cuenta la parte del mes que queda."""
    aplica = [r for r in filas if r['bici'] == bici['id'] and (not comp.get('rodadura') or r['rodadura'] == comp['rodadura'])]
    ev = [e for e in eventos if e['bici'] == bici['id'] and e['pieza'] == comp['nombre'] and e['fecha'][:7] >= comp['mes_base'] and e['origen'] != 'importado']
    if not ev:
        return comp['base'] + sum(r['km'] for r in aplica if r['mes'] > comp['mes_base']), None
    u = max(ev, key=lambda e: e['fecha'])
    f = date.fromisoformat(u['fecha'])
    resto = (calendar.monthrange(f.year, f.month)[1] - f.day) / calendar.monthrange(f.year, f.month)[1]
    return sum(r['km'] for r in aplica if r['mes'] > u['fecha'][:7]) + resto * sum(r['km'] for r in aplica if r['mes'] == u['fecha'][:7]), u


def resumen(hoy=None):
    actual = temporada(_mes_actual(hoy))
    filas, ev, salida = km_filas(), piezas(), []
    for b in cargar_bicis():
        propias = [r for r in filas if r['bici'] == b['id']]
        comps = []
        for c in b['componentes']:
            km, u = _km_comp(b, c, filas, ev)
            anterior = max((e for e in ev if e['bici'] == b['id'] and e['pieza'] == c['nombre']), key=lambda e: e['fecha'], default=None)
            comps.append({'nombre': c['nombre'], 'km': km, 'ultimo': u or anterior})
        maxkm = max((c['km'] for c in comps), default=0) or 1
        for c in comps:
            c['pct'] = round(100 * c['km'] / maxkm)
        salida.append({**b, 'total': b['km_base'] + sum(r['km'] for r in propias), 'temporada': sum(r['km'] for r in propias if temporada(r['mes']) == actual), 'comps': comps,
                       'km_juegos': [{'nombre': j, 'km': sum(r['km'] for r in propias if r['rodadura'] == j)} for j in b['juegos']],
                       'ultimo_mes': max((r['mes'] for r in propias if r['km'] > 0), default=None)})
    return salida


def series():
    """Km por temporada para las gráficas: por bici y juego, y aparte el reparto de cada bici con varios juegos."""
    filas = km_filas()
    temps = sorted({temporada(r['mes']) for r in filas})
    def suma(b, rod, t):
        return round(sum(r['km'] for r in filas if r['bici'] == b and r['rodadura'] == rod and temporada(r['mes']) == t))
    todas, por_juegos = [], []
    for b in cargar_bicis():
        ruedas = b['juegos'] or ['']
        partes = [{'n': b['nombre'] + (f', {j}' if j else ''), 'v': [suma(b['id'], j, t) for t in temps]} for j in ruedas]
        todas += [s for s in partes if any(s['v'])]
        if b['juegos'] and any(any(s['v']) for s in partes):
            desde = next(i for i in range(len(temps)) if any(s['v'][i] for s in partes))
            por_juegos.append({'nombre': b['nombre'], 'cats': [etiqueta_temporada(t) for t in temps[desde:]], 'series': [{'n': s['n'], 'v': s['v'][desde:]} for s in partes]})
    if len(todas) > MAX_SERIES:
        resto = todas[MAX_SERIES - 1:]
        todas = todas[:MAX_SERIES - 1] + [{'n': 'Otras', 'v': [sum(s['v'][i] for s in resto) for i in range(len(temps))]}]
    return {'cats': [etiqueta_temporada(t) for t in temps], 'series': todas, 'por_juegos': por_juegos}


# ---------- Terminal ----------
def _fecha(txt):
    return datetime.strptime(txt, '%d/%m/%Y').date()


def _mes(txt):
    return datetime.strptime(txt, '%m/%Y').strftime('%Y-%m')


def _cli():
    p = argparse.ArgumentParser(description='Anotaciones de bicicletas de VenB')
    s = p.add_subparsers(dest='orden', required=True)
    k = s.add_parser('km')
    k.add_argument('--mes', required=True, help='MM/AAAA')
    k.add_argument('--bici', required=True)
    k.add_argument('--km', type=float, required=True)
    k.add_argument('--juego', default='')
    q = s.add_parser('pieza')
    q.add_argument('--fecha', required=True, help='DD/MM/AAAA')
    q.add_argument('--bici', required=True)
    q.add_argument('--pieza', required=True, action='append')
    q.add_argument('--visita', choices=['mecanico', 'propia'], default='')
    q.add_argument('--taller', default='')
    q.add_argument('--coste', default='')
    q.add_argument('--notas', default='')
    c = s.add_parser('cierre')
    c.add_argument('--mes', required=True, help='MM/AAAA')
    a = p.parse_args()
    if a.orden != 'cierre':
        b = una_bici(a.bici)
        if not b:
            sys.exit(f'Bici desconocida. Opciones: {", ".join(x["id"] for x in cargar_bicis())}')
    if a.orden == 'km':
        if a.juego not in (b['juegos'] or ['']):
            sys.exit(f'Juego de ruedas desconocido. Opciones: {", ".join(b["juegos"]) or "ninguno"}')
        anotar_km(_mes(a.mes), a.bici, a.km, a.juego)
    elif a.orden == 'pieza':
        for pz in a.pieza:
            anotar_pieza(_fecha(a.fecha).isoformat(), a.bici, pz, a.visita, a.taller, a.coste, a.notas)
    else:
        cerrar_mes(_mes(a.mes))
    print('Anotado.')


if __name__ == '__main__':
    _cli()
