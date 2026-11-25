"""Perfiles de puertos: de un track (nuevo o de una ruta del Planificador), las subidas candidatas a puerto con su
Coeficiente de Dificultad (altimetrias.net) y categoría, waypoints propuestos de OpenStreetMap y, por cada puerto
elegido, ficha A4 (mapa y perfil), perfil suelto, mapas ilustrados, GPX y página interactiva.

Cada análisis vive en VenB-datos/puertos/<id>/: entrada/ (el GPX), perfil.npz (track remuestreado y limpio),
analisis.json (cifras de la ruta y perfil reducido), osm_puntos.json (lugares de OSM junto al track), puertos.json
(los tramos y sus puntos, editables), parametros.json (qué generar), salida/<NN_nombre>/ (lo generado),
estado.json y registro.txt. Como el Planificador, analizar y generar van en un proceso aparte:
python puertos.py analizar|generar <carpeta>"""
import glob
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import planificador as PL  # noqa: E402
from planificador import ErrorPlan, EnMarcha, R, _escribir, _estado, _latir, _leer, _nombre_seguro  # noqa: E402,F401

CARPETA = os.path.join(R.PERSISTE, 'puertos')
SALIDAS = {'ficha': 'Ficha A4 (mapa y perfil)', 'perfil': 'Perfil suelto (PNG y SVG)', 'gpx': 'GPX del puerto con waypoints',
           'web': 'Página interactiva', 'alballut': 'Mapa ilustrado (estilo Al-Ballut)', 'personal': 'Mapa personal',
           'tronos': 'Mapa «Juego de Tronos»'}
SALIDAS_DEFECTO = ['ficha', 'perfil', 'gpx']
ESTILOS_FICHA = {k: v for k, v in PL.ESTILOS_INFOGRAFIA.items()}
TIPOS = PL.TIPOS_PARADA
MAX_PUNTOS = 30
# lugares de OSM que se proponen como waypoints: (tipo de VenB, distancia máxima al track en m)
CLASES_OSM = {'pueblo': ('poblacion', 400), 'aldea': ('poblacion', 250), 'puerto': ('puerto', 200), 'cima': ('interes', 250),
              'fuente': ('agua', 60), 'mirador': ('panoramica', 150)}
F_PUNTOS = ('(node["amenity"="drinking_water"]({caja});node["natural"="spring"]["name"]({caja});'
            'node["tourism"="viewpoint"]({caja}););', 'out qt;')


# ------------------------------------------------------------------ análisis guardados

def _carpeta(aid):
    if not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[0-9a-f]{6}', aid or ''):
        raise KeyError(aid)
    d = os.path.join(CARPETA, aid)
    if not os.path.isdir(d):
        raise KeyError(aid)
    return d


def _nuevo(nombre_gpx, origen=None):
    aid = f'{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}'
    d = os.path.join(CARPETA, aid)
    os.makedirs(os.path.join(d, 'entrada'))
    return aid, d


def crear(gpx=None, plan=None):
    """Nuevo análisis desde un GPX subido (werkzeug FileStorage) o desde el track de una ruta del Planificador (su id).
    Lanza el análisis y devuelve el id."""
    if plan:
        try:
            dp = PL._carpeta(plan)
        except KeyError:
            raise ErrorPlan('No encuentro esa ruta del Planificador.')
        e = _leer(dp, 'estado.json', {})
        origen = os.path.join(dp, 'entrada', e.get('gpx') or '')
        if not os.path.isfile(origen):
            raise ErrorPlan('Esa ruta no tiene track.')
        nombre = (_leer(dp, 'parametros.json') or {}).get('nombre') or e.get('nombre') or 'Ruta'
        aid, d = _nuevo(e['gpx'])
        shutil.copy2(origen, os.path.join(d, 'entrada', e['gpx']))
        rg, original = e['gpx'], e.get('gpx_original') or e['gpx']
    else:
        if not gpx or not gpx.filename:
            raise ErrorPlan('Elige el track GPX o una de tus rutas.')
        if os.path.splitext(gpx.filename)[1].lower() != '.gpx':
            raise ErrorPlan('El track debe ser un fichero GPX.')
        rg = _nombre_seguro(gpx.filename, '.gpx')
        aid, d = _nuevo(rg)
        gpx.save(os.path.join(d, 'entrada', rg))
        nombre, original = os.path.splitext(gpx.filename)[0], os.path.basename(gpx.filename)
    ahora = datetime.now().isoformat(timespec='seconds')
    _estado(d, fase='analizando', creado=ahora, inicio_analizar=ahora, gpx=rg, gpx_original=original[:120],
            nombre=nombre[:80], plan=plan)
    _lanzar(d, 'analizar')
    return aid


def _lanzar(d, orden):
    try:
        os.remove(os.path.join(d, PL.DETENER))
    except OSError:
        pass
    log = open(os.path.join(d, 'registro.txt'), 'a', encoding='utf-8')
    log.write(f'\n== {orden} {datetime.now():%d/%m/%Y %H:%M:%S}\n')
    log.flush()
    opciones = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), orden, d], stdout=log, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, cwd=AQUI,
                         env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1', GENERADOR_CACHE=PL.CACHE, MPLBACKEND='Agg'),
                         **opciones)
    log.close()
    PL._procesos[d] = p      # en_marcha y detener del Planificador valen igual
    _latir(d)


def estado(aid):
    d = _carpeta(aid)
    e = _leer(d, 'estado.json', {})
    if e.get('fase') in ('analizando', 'generando') and not PL.en_marcha(d):
        e = _leer(d, 'estado.json', {})
        p = PL._procesos.get(d)
        if e.get('fase') in ('analizando', 'generando') and (p is None or p.returncode not in (0, None)):
            e = _estado(d, fase='error' if e['fase'] == 'analizando' else 'listo',
                        error='El proceso se interrumpió. Vuelve a intentarlo.' if p is None else 'El proceso terminó con un error.')
    e['id'] = aid
    e['registro'] = PL.registro(d)
    return e


def detener(aid):
    d = _carpeta(aid)
    e = _leer(d, 'estado.json', {})
    if e.get('fase') not in ('analizando', 'generando'):
        raise ErrorPlan('No hay ningún proceso en marcha.')
    with open(os.path.join(d, PL.DETENER), 'w', encoding='utf-8') as f:
        f.write(datetime.now().isoformat(timespec='seconds'))
    p = PL._procesos.get(d)
    if p is not None and p.poll() is None:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
    try:
        os.remove(os.path.join(d, 'latido.txt'))
    except OSError:
        pass
    PL._procesos.pop(d, None)
    if e['fase'] == 'generando':
        _estado(d, fase='listo', error=None)
    elif os.path.exists(os.path.join(d, 'analisis.json')):
        _estado(d, fase='listo', error=None)
    else:
        _estado(d, fase='error', error='Has detenido el análisis. Lo descargado queda guardado: vuelve a empezar para seguir desde ahí.')


def lista():
    if not os.path.isdir(CARPETA):
        return []
    salida = []
    for aid in sorted(os.listdir(CARPETA), reverse=True):
        try:
            e = estado(aid)
        except KeyError:
            continue
        d = os.path.join(CARPETA, aid)
        a = _leer(d, 'analisis.json', {}) or {}
        ps = _leer(d, 'puertos.json', []) or []
        e.update(total_km=a.get('total_km'), total_asc=a.get('total_asc'), n_puertos=sum(1 for p in ps if p.get('incluir')))
        salida.append(e)
    return salida


def de_plan(pid):
    """Id del análisis de puertos más reciente de una ruta del Planificador; si no hay, lo crea."""
    for e in lista():
        if e.get('plan') == pid and e.get('fase') != 'error':
            return e['id']
    return crear(plan=pid)


def borrar(aid):
    d = _carpeta(aid)
    if PL.en_marcha(d):
        raise ErrorPlan('Este análisis se está procesando: espera a que termine.')
    shutil.rmtree(d)


def datos(aid):
    """(análisis, puertos, parámetros) para la página."""
    d = _carpeta(aid)
    a = _leer(d, 'analisis.json')
    if a:
        a = {**a, 'perfil': _perfil_vista(d) or a.get('perfil'), **_extremos(d)}
    return a, _leer(d, 'puertos.json', []) or [], parametros(aid)


def _extremos(d):
    """Altitudes mínima y máxima reales (sin suavizar), para el eje del perfil de la página."""
    try:
        e = _perfil_npz(d)['ele']
        return {'alt_min': round(float(e.min())), 'alt_max': round(float(e.max()))}
    except Exception:
        return {}


def _perfil_vista(d, puntos=600):
    """Perfil de toda la ruta para la página, suavizado: en una franja estrecha, las ondas de pocos metros que
    quedan en las altitudes se ven como dientes. Solo es la vista; las cifras salen del perfil sin suavizar."""
    try:
        import numpy as np
        from generador.datos import _suavizar
        t = _perfil_npz(d)
        km, ele = t['km'], t['ele']
        paso_m = float(np.median(np.diff(km))) * 1000
        ventana = max(300.0, km[-1] * 1000 / 120)       # unos 300 m en una ruta corta; ~1,7 km en una de 200 km
        e = _suavizar(ele, ventana, paso_m)
        i = np.unique(np.linspace(0, len(km) - 1, min(puntos, len(km))).round().astype(int))
        return [[round(float(km[j]), 2), round(float(e[j]))] for j in i]
    except Exception:
        return None


def parametros(aid):
    p = _leer(_carpeta(aid), 'parametros.json') or {}
    return {'salidas': p.get('salidas') or list(SALIDAS_DEFECTO), 'estilo_mapa': p.get('estilo_mapa') or 'ign_mtn',
            'paleta': p.get('paleta') or 'verde', 'club': p.get('club') if 'club' in p else None}


# ------------------------------------------------------------------ perfil y cálculos

def _perfil_npz(d):
    import numpy as np
    z = np.load(os.path.join(d, 'perfil.npz'))
    return {k: z[k] for k in z.files}


def _alt(t, km):
    import numpy as np
    return float(np.interp(km, t['km'], t['ele']))


def _con_cifras(t, p):
    """Puerto con sus cifras recalculadas desde el perfil (al analizar y al guardar cambios)."""
    from generador.puertos import datos_puerto
    c = datos_puerto(t['km'], t['ele'], p['km0'], p['km1'])
    pts = []
    for x in p.get('puntos') or []:
        k = min(max(float(x['km']), p['km0']), p['km1'])
        pts.append({'nombre': str(x['nombre'])[:60], 'km': round(k, 3), 'tipo': x.get('tipo') if x.get('tipo') in TIPOS else '',
                    'alt': round(_alt(t, k))})
    pts.sort(key=lambda x: x['km'])
    return {**c, 'id': p['id'], 'nombre': str(p.get('nombre') or 'Puerto')[:80], 'subtitulo': str(p.get('subtitulo') or '')[:120],
            'incluir': bool(p.get('incluir', True)), 'manual': bool(p.get('manual')), 'puntos': pts}


def _osm_puntos(track):
    """Lugares con nombre junto al track (pueblos, aldeas, puertos, cimas, fuentes y miradores) con su km en el track."""
    import numpy as np
    from generador import osm
    from generador.puertos import km_en_track
    celdas = osm._celdas(track, 1)
    osm._descargar_zonas([(celdas, [osm.F_PUEBLOS, osm.F_ALDEAS, osm.F_PUERTOS, osm.F_CIMAS, F_PUNTOS])])
    lugares = []
    for filtro, clase in ((osm.F_PUEBLOS, 'pueblo'), (osm.F_ALDEAS, 'aldea'), (osm.F_PUERTOS, 'puerto'), (osm.F_CIMAS, 'cima'), (F_PUNTOS, None)):
        for el in osm._por_celdas(*filtro, celdas=celdas):
            c = osm._centro(el)
            if not c:
                continue
            tags = el.get('tags', {})
            cl = clase or ('mirador' if tags.get('tourism') == 'viewpoint' else 'fuente')
            nombre = tags.get('name:es') or tags.get('name') or {'fuente': 'Fuente', 'mirador': 'Mirador'}.get(cl)
            if not nombre:
                continue
            tipo, maximo = CLASES_OSM[cl]
            km, dist = km_en_track(c[0], c[1], track.lat, track.lon, track.km)
            if km is None or dist > maximo:
                continue
            lugares.append({'nombre': nombre, 'clase': cl, 'tipo': tipo, 'lat': c[0], 'lon': c[1], 'km': round(km, 3),
                            'dist': round(dist), 'ele': osm._num(tags.get('ele'))})
    lugares.sort(key=lambda x: x['km'])
    return lugares


def _cerca(lugares, km, radio, clases=None):
    """El lugar más cercano a un km del track (dentro de `radio` km), de las clases dadas."""
    mejor = None
    for l in lugares:
        if clases and l['clase'] not in clases:
            continue
        dk = abs(l['km'] - km)
        if dk <= radio and (mejor is None or dk < abs(mejor['km'] - km)):
            mejor = l
    return mejor


def proponer(lugares, km0, km1, n):
    """Nombre, subtítulo y puntos propuestos para la subida entre km0 y km1 (n: número de subida, para el nombre)."""
    cima = _cerca(lugares, km1, 0.6, ('puerto',)) or _cerca(lugares, km1, 0.4, ('cima',))
    pie = _cerca(lugares, km0, 1.0, ('pueblo', 'aldea'))
    desde = pie or _cerca(lugares, km0, 3.0, ('pueblo', 'aldea'))
    arriba = _cerca(lugares, km1, 1.2, ('pueblo', 'aldea'))
    if cima:
        nombre = cima['nombre']
    elif arriba:
        nombre = f'Subida a {arriba["nombre"]}'
    else:
        nombre = f'Subida {n} (km {km0:.1f})'.replace('.', ',')
    subtitulo = f'Desde {desde["nombre"]}' if desde else ''
    puntos = [{'nombre': pie['nombre'] if pie else 'Pie del puerto', 'km': km0, 'tipo': 'salida'}]
    for l in lugares:
        if km0 + 0.25 < l['km'] < km1 - 0.25 and all(abs(l['km'] - x['km']) >= 0.3 and l['nombre'] != x['nombre'] for x in puntos):
            puntos.append({'nombre': l['nombre'], 'km': l['km'], 'tipo': l['tipo']})
    puntos.append({'nombre': cima['nombre'] if cima else (arriba['nombre'] if arriba else 'Cima'), 'km': km1, 'tipo': 'puerto'})
    return nombre, subtitulo, puntos[:MAX_PUNTOS]


def guardar(aid, lista_puertos):
    """Guarda los tramos editados en la página (nombre, km del pie y de la cima, incluir, puntos) y recalcula sus cifras."""
    d = _carpeta(aid)
    if PL.en_marcha(d):
        raise EnMarcha('Se está procesando: espera a que termine.')
    t = _perfil_npz(d)
    total = float(t['km'][-1])
    salida, ids = [], set()
    for p in lista_puertos:
        try:
            km0, km1 = float(p['km0']), float(p['km1'])
        except (KeyError, TypeError, ValueError):
            raise ErrorPlan('Cada tramo necesita el km del pie y el de la cima.')
        if not (0 <= km0 < km1 <= total + 0.01):
            raise ErrorPlan(f'«{p.get("nombre") or "Tramo"}»: el pie debe estar antes que la cima, entre el km 0 y el {total:.1f}.'.replace('.', ',', 1))
        if km1 - km0 < 0.2:
            raise ErrorPlan(f'«{p.get("nombre") or "Tramo"}»: el tramo debe medir al menos 200 m.')
        pid = str(p.get('id') or '')
        if not re.fullmatch(r'[a-z0-9]{1,12}', pid) or pid in ids:
            pid = secrets.token_hex(3)
        ids.add(pid)
        puntos = []
        for x in (p.get('puntos') or [])[:MAX_PUNTOS]:
            nombre = ' '.join(str(x.get('nombre') or '').split())
            if not nombre:
                continue
            try:
                puntos.append({'nombre': nombre, 'km': float(x['km']), 'tipo': x.get('tipo') or ''})
            except (KeyError, TypeError, ValueError):
                raise ErrorPlan(f'Punto «{nombre}»: km no válido.')
        salida.append(_con_cifras(t, {**p, 'id': pid, 'km0': km0, 'km1': km1, 'puntos': puntos}))
    salida.sort(key=lambda x: x['km0'])
    _escribir(d, 'puertos.json', salida)
    return salida


def nuevo_tramo(aid, km0, km1):
    """Añade un tramo elegido a mano (por ejemplo, una subida que no llega a puerto), con puntos de OSM."""
    d = _carpeta(aid)
    ps = _leer(d, 'puertos.json', []) or []
    nombre, sub, puntos = proponer(_leer(d, 'osm_puntos.json', []) or [], km0, km1, len(ps) + 1)
    ps.append({'id': secrets.token_hex(3), 'nombre': nombre, 'subtitulo': sub, 'km0': km0, 'km1': km1, 'incluir': True,
               'manual': True, 'puntos': puntos})
    return guardar(aid, ps)


def proponer_puntos(aid, pid):
    """Vuelve a proponer los puntos de OSM de un tramo (con sus km actuales)."""
    d = _carpeta(aid)
    ps = _leer(d, 'puertos.json', []) or []
    for p in ps:
        if p['id'] == pid:
            _, _, p['puntos'] = proponer(_leer(d, 'osm_puntos.json', []) or [], p['km0'], p['km1'], 0)
    return guardar(aid, ps)


def perfil_tramo(aid, km0, km1, n=300):
    """[km desde el pie, altitud] del tramo, para la vista previa al editarlo."""
    import numpy as np
    t = _perfil_npz(_carpeta(aid))
    k = np.linspace(km0, km1, n)
    return [[round(float(a - km0), 3), round(float(b), 1)] for a, b in zip(k, np.interp(k, t['km'], t['ele']))]


def trazado(aid, paso_m=40):
    """[[lat, lon, km]] para elegir puntos en el mapa (los km son los del perfil)."""
    t = _perfil_npz(_carpeta(aid))
    paso = max(1, int(round(paso_m / 25)))
    return [[round(float(a), 5), round(float(b), 5), round(float(c), 3)]
            for a, b, c in zip(t['lat'][::paso], t['lon'][::paso], t['km'][::paso])]


def guardar_parametros(aid, datos_):
    d = _carpeta(aid)
    salidas = [s for s in datos_.get('salidas') or [] if s in SALIDAS]
    if not salidas:
        raise ErrorPlan('Elige al menos un documento.')
    p = {'salidas': salidas, 'estilo_mapa': datos_.get('estilo_mapa') if datos_.get('estilo_mapa') in ESTILOS_FICHA else 'ign_mtn',
         'paleta': datos_.get('paleta') if datos_.get('paleta') in PL.PALETAS else 'verde',
         # VenB Rutas: club u organizador cuya marca llevan los documentos ('' = la de VenB)
         'club': datos_.get('club') if R.RUTAS and datos_.get('club') and PL._club_valido(datos_.get('club')) else ''}
    _escribir(d, 'parametros.json', p)
    return p


def generar(aid, datos_):
    d = _carpeta(aid)
    if PL.en_marcha(d):
        raise EnMarcha('Ya se está procesando.')
    if datos_.get('puertos') is not None:
        guardar(aid, datos_['puertos'])
    guardar_parametros(aid, datos_)
    if not any(p.get('incluir') for p in _leer(d, 'puertos.json', []) or []):
        raise ErrorPlan('Marca al menos un puerto para generar sus documentos.')
    _estado(d, fase='generando', error=None, aviso_mapas=None, inicio_generar=datetime.now().isoformat(timespec='seconds'))
    _lanzar(d, 'generar')


# ------------------------------------------------------------------ documentos generados

def _slug(texto):
    import unicodedata
    t = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '_', t).strip('_')[:40] or 'puerto'


TITULOS = [('ficha_', 'Ficha del puerto'), ('perfil_', 'Perfil'), ('mapa_ilustrado', 'Mapa ilustrado (Al-Ballut)'),
           ('mapa_personal', 'Mapa personal'), ('mapa_tronos', 'Mapa «Juego de Tronos»'), ('ruta_interactiva', 'Página interactiva'),
           ('PUERTO_', 'GPX con waypoints')]


def documentos(aid):
    """Por puerto generado: {'carpeta', 'nombre', 'docs': [{'titulo', 'imagen', 'ficheros': [(formato, ruta relativa)]}]}."""
    d = os.path.join(_carpeta(aid), 'salida')
    if not os.path.isdir(d):
        return []
    salida = []
    for c in sorted(os.listdir(d)):
        dc = os.path.join(d, c)
        if not os.path.isdir(dc):
            continue
        info = _leer(dc, 'puerto.json', {}) or {}
        grupos = {}
        for f in sorted(os.listdir(dc)):
            base, ext = os.path.splitext(f)
            if ext in ('.json', '.zip') or f.startswith('_'):
                continue
            grupos.setdefault(base, []).append((PL.FORMATOS.get(ext.lower(), ext[1:].upper()), f'{c}/{f}'))
        docs = []
        for base, fs in grupos.items():
            titulo = next((t for k, t in TITULOS if base.startswith(k)), base)
            docs.append({'titulo': titulo, 'imagen': next((n for _, n in fs if n.endswith('.png')), None), 'ficheros': fs,
                         'orden': next((i for i, (k, _) in enumerate(TITULOS) if base.startswith(k)), 9)})
        docs.sort(key=lambda x: x['orden'])
        salida.append({'carpeta': c, 'nombre': info.get('nombre') or c, 'categoria': info.get('categoria'), 'coef': info.get('coef'), 'docs': docs})
    return salida


def fichero(aid, ruta):
    partes = ruta.split('/')
    if len(partes) != 2 or any(not x or x.startswith('.') or x != os.path.basename(x) for x in partes):
        raise KeyError(ruta)
    f = os.path.join(_carpeta(aid), 'salida', *partes)
    if not os.path.isfile(f):
        raise KeyError(ruta)
    return f


def zip_salida(aid):
    d = _carpeta(aid)
    s = os.path.join(d, 'salida')
    ruta = os.path.join(d, _nombre_seguro('puertos_' + (_leer(d, 'estado.json', {}).get('nombre') or 'ruta'), '.zip'))
    with zipfile.ZipFile(ruta, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(glob.glob(os.path.join(s, '*', '*'))):
            if not f.endswith('.json'):
                z.write(f, os.path.relpath(f, s))
    return ruta


# ------------------------------------------------------------------ trabajo en segundo plano

def _analizar(d):
    import numpy as np
    from generador.datos import leer_gpx
    from generador.puertos import detectar
    e = _leer(d, 'estado.json', {})
    print('Leyendo el track y consultando las altitudes del terreno…', flush=True)
    tr = leer_gpx(os.path.join(d, 'entrada', e['gpx']))
    print(f'  altitudes: {tr.fuente_altitud}', flush=True)
    np.savez_compressed(os.path.join(d, 'perfil.npz'), km=tr.km, ele=tr.ele, lat=tr.lat, lon=tr.lon,
                        orig_km=tr.orig_km, orig_lat=tr.orig_lat, orig_lon=tr.orig_lon)
    t = {'km': tr.km, 'ele': tr.ele}
    print('Buscando subidas…', flush=True)
    subidas = detectar(tr.km, tr.ele)
    print(f'  {len(subidas)} subidas con categoría de puerto', flush=True)
    avisos = []
    print('Lugares de OpenStreetMap junto al track (la primera vez en una zona nueva puede tardar)…', flush=True)
    try:
        lugares = _osm_puntos(tr)
        print(f'  {len(lugares)} lugares', flush=True)
    except Exception as ex:
        print(f'  aviso: sin datos de OpenStreetMap ({ex})', flush=True)
        lugares = []
        avisos.append('No se han podido consultar los lugares de OpenStreetMap: los puertos llevan solo el pie y la cima. '
                      'Añade puntos a mano o vuelve a analizar más tarde.')
    _escribir(d, 'osm_puntos.json', lugares)
    puertos = []
    for i, s in enumerate(subidas, 1):
        nombre, sub, puntos = proponer(lugares, s['km0'], s['km1'], i)
        puertos.append(_con_cifras(t, {'id': secrets.token_hex(3), 'nombre': nombre, 'subtitulo': sub, 'km0': s['km0'], 'km1': s['km1'],
                                       'incluir': True, 'puntos': puntos}))
    _escribir(d, 'puertos.json', puertos)
    sube = float(np.clip(np.diff(tr.ele), 0, None).sum())
    paso = max(1, len(tr.km) // 600)
    a = {'nombre': e.get('nombre') or tr.nombre, 'total_km': round(float(tr.total_km), 2), 'total_asc': round(sube),
         'fuente_altitud': tr.fuente_altitud, 'avisos': avisos,
         'perfil': [[round(float(k), 2), round(float(v))] for k, v in zip(tr.km[::paso], tr.ele[::paso])]}
    _escribir(d, 'analisis.json', a)
    print(f'Hecho: {tr.total_km:.1f} km, +{sube:.0f} m', flush=True)
    _estado(d, fase='listo', error=None)


def _marca(club=''):
    if R.RUTAS and club:     # VenB Rutas: la marca del club, con la de VenB siempre al lado (como en el Planificador)
        import clubes
        m = clubes.marca(club)
        if m:
            return {**m, 'texto_pie': m.get('texto') or ''}
    aj = R.ajustes()
    marca = dict(aj.get('planificador_marca') or {})
    if marca.get('logo') and not os.path.isabs(os.path.expanduser(marca['logo'])):
        marca['logo'] = os.path.join(AQUI, 'generador', 'recursos', marca['logo'])
    marca['logo'] = os.path.expanduser(marca.get('logo') or '') or None
    if not marca['logo']:
        marca.pop('logo')
    marca['texto_pie'] = marca.get('texto') or ''
    return marca


def _gpx_tramo(t, km0, km1, ruta, nombre):
    """GPX del tramo con las altitudes del perfil (limpias): base del Proyecto para mapas y página interactiva."""
    import numpy as np
    from xml.sax.saxutils import escape
    if 'orig_km' in t:      # los puntos del GPX original: la longitud del tramo es la del perfil
        sel = (t['orig_km'] > km0) & (t['orig_km'] < km1)
        km = np.r_[km0, t['orig_km'][sel], km1]
        lat = np.r_[np.interp(km0, t['km'], t['lat']), t['orig_lat'][sel], np.interp(km1, t['km'], t['lat'])]
        lon = np.r_[np.interp(km0, t['km'], t['lon']), t['orig_lon'][sel], np.interp(km1, t['km'], t['lon'])]
        ele = np.interp(km, t['km'], t['ele'])
    else:
        sel = (t['km'] > km0) & (t['km'] < km1)
        km = np.r_[km0, t['km'][sel], km1]
        lat, lon, ele = (np.interp(km, t['km'], t[x]) for x in ('lat', 'lon', 'ele'))
    pts = '\n'.join(f'<trkpt lat="{a:.6f}" lon="{b:.6f}"><ele>{c:.1f}</ele></trkpt>' for a, b, c in zip(lat, lon, ele))
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="VenB" xmlns="http://www.topografix.com/GPX/1/1">\n'
                f'<trk><name>{escape(nombre)}</name><trkseg>\n{pts}\n</trkseg></trk>\n</gpx>\n')


def _generar_puerto(d, t, p, n, par, marca):
    import numpy as np
    from generador import altimetria as A
    from generador.proyecto import Proyecto
    from generador.puertos import datos_puerto
    carpeta = f'{n:02d}_{_slug(p["nombre"])}'
    sd = os.path.join(d, 'salida', carpeta)
    os.makedirs(sd, exist_ok=True)
    km0, km1 = p['km0'], p['km1']
    sel = (t['km'] > km0) & (t['km'] < km1)
    km = np.r_[km0, t['km'][sel], km1]
    sub = {k: np.interp(km, t['km'], t[k]) for k in ('lat', 'lon', 'ele')}
    sub['km'] = km - km0
    rel = datos_puerto(sub['km'], sub['ele'], 0, km1 - km0)       # cifras con los km desde el pie
    puntos = [{'n': i, 'nombre': x['nombre'], 'km': x['km'] - km0, 'alt': x['alt'], 'tipo': x['tipo']}
              for i, x in enumerate(p['puntos'], 1)]
    _escribir(sd, 'puerto.json', {k: p[k] for k in ('nombre', 'subtitulo', 'km0', 'km1', 'categoria', 'coef', 'coef_100')})
    sal = par['salidas']
    if 'ficha' in sal:
        print('  ficha A4 (mapa y perfil)…', flush=True)
        A.ficha(rel, sub, puntos, p['nombre'], p['subtitulo'], os.path.join(sd, 'ficha_puerto'), par['estilo_mapa'], marca)
    if 'perfil' in sal:
        print('  perfil…', flush=True)
        A.perfil(rel, sub['km'], sub['ele'], puntos, p['nombre'], p['subtitulo'], os.path.join(sd, 'perfil_puerto'), marca)
    estilos = [s for s in ('alballut', 'personal', 'tronos') if s in sal]
    if not (estilos or 'gpx' in sal or 'web' in sal):
        return None
    # mapas ilustrados, GPX y página interactiva: el motor del Planificador, con el tramo como ruta y sin horarios
    _gpx_tramo(t, km0, km1, os.path.join(sd, '_tramo.gpx'), p['nombre'])
    lista = [{'nombre': x['nombre'], 'km_hoja': round(x['km'] - km0, 3), 'control': '', 'tipo': x['tipo']} for x in p['puntos']]
    if not lista or lista[0]['km_hoja'] > 0.001:
        lista.insert(0, {'nombre': 'Pie del puerto', 'km_hoja': 0.0, 'control': '', 'tipo': 'salida'})
    if lista[-1]['km_hoja'] < km1 - km0 - 0.001:
        lista.append({'nombre': 'Cima', 'km_hoja': round(km1 - km0, 3), 'control': '', 'tipo': 'puerto'})
    tipos = {f"{x['nombre']}@{x['km_hoja']:g}": x.pop('tipo') for x in lista}
    cfg = {'nombre': p['nombre'], 'subtitulo': ' · '.join(x for x in (p['subtitulo'], f"{p['categoria'] or 'Sin categoría'} · coeficiente {p['coef']}") if x),
           'gpx': '_tramo.gpx', 'hoja': None, 'puntos': lista, 'meta': {}, 'salida': datetime.now().replace(hour=9, minute=0, second=0, microsecond=0),
           'carpeta_salida': '.', 'ajuste_km': 'ninguno', 'limite_horas': 1, 'horario': {'salida': False, 'limite': False},
           'regla': None, 'destacados': [], 'paradas': {'por_defecto_min': 0},
           'tipos_parada': {k: v for k, v in tipos.items() if v}, 'velocidades': None,
           'altitud': {'fuente': 'gpx', 'suavizado_m': 25},
           'mapa': {'titulo': p['nombre'], 'estilos': estilos, 'paleta': par['paleta'], 'servicios': False, 'orientacion': 'auto'},
           'marca': {k: v for k, v in marca.items() if k != 'texto_pie'}}
    proyecto = Proyecto(cfg=cfg, base=sd)
    plan = proyecto.calcular()
    plan.puerto = rel
    for pt in plan.puntos:
        pt.extra['mostrar'] = True
    aviso = None
    if estilos:
        from generador.osm import elementos
        tr = plan.track
        osm = None
        print('  datos geográficos (IGN y OpenStreetMap)…', flush=True)
        try:
            osm = elementos(tr, (tr.lat.min() - 0.08, tr.lon.min() - 0.1, tr.lat.max() + 0.08, tr.lon.max() + 0.1))
            if osm.get('fallos'):
                aviso = PL._aviso_mapas(osm['fallos'], osm.get('motivo_fallo'))
        except Exception as ex:
            aviso = PL._aviso_mapas(None, str(ex))
        print('  mapas ilustrados…', flush=True)
        from generador.ilustrado import generar as g
        g(proyecto, plan, osm)
    if 'gpx' in sal or 'web' in sal:
        from generador.web import _mayus, gpx_waypoints
        from xml.sax.saxutils import escape
        n0, texto = gpx_waypoints(proyecto, plan)
        nombre_gpx = f"PUERTO_{_mayus(p['nombre'], fichero=True) or 'PUERTO'}_WP.gpx"
        if 'gpx' in sal:
            print('  GPX con waypoints…', flush=True)
            with open(os.path.join(sd, nombre_gpx), 'w', encoding='utf-8') as f:
                f.write(texto.replace(f'<name>{escape(n0[:-4])}</name>', f'<name>{escape(_mayus(p["nombre"]))}</name>'))
    if 'web' in sal:
        print('  página interactiva…', flush=True)
        from generador.web import generar as g
        g(proyecto, plan)
    for f in glob.glob(os.path.join(sd, '_tramo.gpx')):
        os.remove(f)
    return aviso


def _generar(d):
    par = _leer(d, 'parametros.json') or {'salidas': SALIDAS_DEFECTO, 'estilo_mapa': 'ign_mtn', 'paleta': 'verde'}
    t = _perfil_npz(d)
    elegidos = [p for p in _leer(d, 'puertos.json', []) or [] if p.get('incluir')]
    sd = os.path.join(d, 'salida')
    if os.path.isdir(sd):
        shutil.rmtree(sd)
    os.makedirs(sd)
    marca = _marca(par.get('club') or '')
    avisos = []
    for n, p in enumerate(elegidos, 1):
        print(f'Puerto {n}/{len(elegidos)}: {p["nombre"]}…', flush=True)
        aviso = _generar_puerto(d, t, p, n, par, marca)
        if aviso and aviso not in avisos:
            avisos.append(aviso)
    _estado(d, fase='hecho', error=None, aviso_mapas=' '.join(avisos) or None, generado=datetime.now().isoformat(timespec='seconds'))
    print('Hecho.', flush=True)


def _trabajo(orden, d):
    import threading
    parar = threading.Event()

    def latido():
        n = 0
        while not parar.is_set():
            if os.path.exists(os.path.join(d, PL.DETENER)):
                print('\nDetenido.', flush=True)
                try:
                    os.remove(os.path.join(d, 'latido.txt'))
                except OSError:
                    pass
                os._exit(3)
            if n % PL.LATIDO_S == 0:
                _latir(d)
            n += 1
            parar.wait(1)
    threading.Thread(target=latido, daemon=True).start()
    try:
        (_analizar if orden == 'analizar' else _generar)(d)
    except Exception as ex:
        import traceback
        traceback.print_exc()
        _estado(d, fase='error' if orden == 'analizar' else 'listo', error=str(ex) or ex.__class__.__name__)
        sys.exit(1)
    finally:
        parar.set()
        try:
            os.remove(os.path.join(d, 'latido.txt'))
        except OSError:
            pass


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] not in ('analizar', 'generar'):
        sys.exit(__doc__)
    _trabajo(sys.argv[1], os.path.abspath(sys.argv[2]))
