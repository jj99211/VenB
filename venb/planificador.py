"""Planificador de rutas: GPX + hoja de ruta (PDF, ODT, ODS, XLSX o CSV) -> plan de tiempos, infografías,
mapas ilustrados y página interactiva. El motor es el paquete generador/ (del proyecto GENERADOR_MAPAS).

Cada plan vive en VenB-datos/planificador/<id>/: entrada/ (lo subido), puntos.json (si se editan a mano), analisis.json, parametros.json,
salida/ (lo generado), estado.json y registro.txt. La caché de teselas, altitudes y OpenStreetMap va en
~/.venb/mapas/cache. Analizar y generar pueden tardar minutos (descargas), así que se hacen en un proceso
aparte que la página consulta:  python planificador.py analizar|generar <carpeta del plan>"""
import glob
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import unicodedata
import zipfile
from datetime import date, datetime, timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'scripts'))
import rutas as R  # noqa: E402

PLANES = os.path.join(R.PERSISTE, 'planificador')
CACHE = os.path.join(R.INTERNO, 'mapas', 'cache')
os.environ.setdefault('GENERADOR_CACHE', CACHE)
EXT_GPX = ('.gpx',)
EXT_HOJA = ('.pdf', '.odt', '.ods', '.xlsx', '.xlsm', '.csv')
SALIDAS = {'tabla': 'Tabla de tiempos (Excel)', 'infografia': 'Infografías', 'alballut': 'Mapa ilustrado (estilo Al-Ballut)',
           'personal': 'Mapa personal', 'tronos': 'Mapa «Juego de Tronos»', 'web': 'Página interactiva'}
MODALIDADES = {'brevet': 'Brevet (BRM)', 'sr': 'Super Randonnée', 'sb': 'Super Brevet (1.200 km o más)', 'libre': 'Recorrido libre'}
DISTANCIAS_BREVET = [200, 300, 400, 600, 1000]
MAX_ETAPAS = 7          # días; como mucho MAX_ETAPAS - 1 paradas para dormir
TIPOS_PARADA = {'': '—', 'salida': 'Salida', 'cafe': 'Café', 'comida': 'Comida', 'dormir': 'Dormir', 'agua': 'Agua', 'cruce': 'Cruce', 'peligro': 'Peligro',
                'interes': 'Punto de interés', 'poblacion': 'Población', 'panoramica': 'Panorámica', 'puerto': 'Puerto', 'llegada': 'Llegada', 'otra': 'Otra'}
PALETAS = ['verde', 'acuarela', 'bosque', 'pizarra', 'alballut']
ESTILOS_INFOGRAFIA = {'ign_mtn': 'IGN: topográfico (MTN)', 'ign_base': 'IGN Base', 'ign_orto': 'IGN: ortofoto con rótulos',
                      'topo': 'Topográfico (OpenStreetMap)', 'osm': 'OpenStreetMap', 'hot': 'Humanitario (OpenStreetMap)'}
_procesos = {}


class ErrorPlan(Exception):
    pass


class EnMarcha(ErrorPlan):
    """El plan ya tiene un análisis o una generación en marcha: la página muestra su progreso."""


LATIDO_S = 15       # el proceso de análisis o generación marca que sigue vivo cada LATIDO_S segundos
DETENER = 'detener.txt'     # si aparece en la carpeta del plan, el proceso en marcha termina enseguida


def _latir(d):
    try:
        with open(os.path.join(d, 'latido.txt'), 'w', encoding='utf-8') as f:
            f.write(datetime.now().isoformat(timespec='seconds'))
    except OSError:
        pass


def _tipo(t):
    """Tipo de parada válido o ''."""
    return t if t in TIPOS_PARADA else ''


# ------------------------------------------------------------------ planes guardados

def regla_de(p):
    """Regla de cierres de unos parámetros: RM (brevet o Super Brevet, con su tiempo oficial, que desde la 3.58 no se
    cambia: el ritmo propio va en el tiempo objetivo) o None (SR y libre: proporcional; en el libre mandan las horas de
    la hoja, si las trae)."""
    modalidad, dist = p.get('modalidad'), p.get('distancia_brm')
    if modalidad == 'brevet' and dist == 1200:      # planes anteriores a la 3.43: el 1200 era un brevet
        modalidad = 'sb'
    if modalidad in ('brevet', 'sb') and dist:
        return {'distancia': dist, 'prefijo': 'SB' if modalidad == 'sb' else 'BRM'}
    return None


def ver_etapas(modalidad, dist):
    """Se puede organizar en varias etapas: BRM de 400 km o más, SR, Super Brevets y recorridos libres."""
    return modalidad in ('sr', 'sb', 'libre') or (modalidad == 'brevet' and (dist or 0) >= 400)


def _carpeta(pid):
    if not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[0-9a-f]{6}', pid or ''):
        raise KeyError(pid)
    d = os.path.join(PLANES, pid)
    if not os.path.isdir(d):
        raise KeyError(pid)
    return d


def _leer(d, nombre, defecto=None):
    try:
        with open(os.path.join(d, nombre), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def _escribir(d, nombre, datos):
    tmp = os.path.join(d, nombre + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, os.path.join(d, nombre))


def _estado(d, **cambios):
    e = _leer(d, 'estado.json', {})
    e.update(cambios, actualizado=datetime.now().isoformat(timespec='seconds'))
    _escribir(d, 'estado.json', e)
    return e


def _nombre_seguro(nombre, ext):
    base = unicodedata.normalize('NFKD', os.path.splitext(os.path.basename(nombre))[0]).encode('ascii', 'ignore').decode()
    base = re.sub(r'[^A-Za-z0-9_.-]+', '_', base).strip('._')[:60] or 'fichero'
    return base + ext


def crear(gpx, hoja=None, evento=None):
    """gpx y hoja: ficheros subidos (werkzeug FileStorage). Sin hoja, el plan empieza con la salida y la meta del
    track y los puntos se añaden a mano. Devuelve el id del plan y lanza el análisis."""
    eg = os.path.splitext(gpx.filename or '')[1].lower()
    hoja = hoja if hoja and hoja.filename else None
    eh = os.path.splitext(hoja.filename)[1].lower() if hoja else ''
    if eg not in EXT_GPX:
        raise ErrorPlan('El track debe ser un fichero GPX.')
    if hoja and eh not in EXT_HOJA:
        raise ErrorPlan('La hoja de ruta debe ser PDF, ODT, ODS, XLSX o CSV.')
    pid = f'{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}'
    d = os.path.join(PLANES, pid)
    os.makedirs(os.path.join(d, 'entrada'))
    rg = _nombre_seguro(gpx.filename, eg)
    rh = _nombre_seguro(hoja.filename, eh) if hoja else None
    if rg == rh:
        rh = 'hoja_' + rh
    gpx.save(os.path.join(d, 'entrada', rg))
    if hoja:
        hoja.save(os.path.join(d, 'entrada', rh))
    _estado(d, fase='analizando', creado=datetime.now().isoformat(timespec='seconds'), inicio_analizar=datetime.now().isoformat(timespec='seconds'), gpx=rg, hoja=rh,
            nombre=os.path.splitext(gpx.filename)[0][:80], gpx_original=os.path.basename(gpx.filename)[:120],
            hoja_original=os.path.basename(hoja.filename)[:120] if hoja else '', evento=evento)
    _lanzar(d, 'analizar')
    return pid


def _lanzar(d, orden):
    """Proceso aparte, con su registro; sobrevive a la petición, no a VenB (se marca como interrumpido)."""
    try:
        os.remove(os.path.join(d, DETENER))
    except OSError:
        pass
    log = open(os.path.join(d, 'registro.txt'), 'a', encoding='utf-8')
    log.write(f'\n== {orden} {datetime.now():%d/%m/%Y %H:%M:%S}\n')
    log.flush()
    opciones = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), orden, d], stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         cwd=AQUI, env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1', GENERADOR_CACHE=CACHE, MPLBACKEND='Agg'), **opciones)
    log.close()
    _procesos[d] = p
    _latir(d)


def en_marcha(d):
    """¿Hay un análisis o una generación en marcha? Si lo lanzó esta VenB, se pregunta al proceso; si no (VenB se
    cerró y se volvió a abrir, o hay otra VenB, como VenB Rutas, sobre los mismos datos), por su latido reciente."""
    p = _procesos.get(d)
    if p is not None:
        return p.poll() is None
    try:
        return datetime.now().timestamp() - os.path.getmtime(os.path.join(d, 'latido.txt')) < LATIDO_S * 4
    except OSError:
        return False


def detener(pid):
    """Detiene el análisis o la generación en marcha. Vale aunque el proceso no sea de esta VenB (se reabrió): el
    proceso vigila DETENER cada segundo y termina; si es de esta VenB, además se termina directamente.
    Lo descargado (teselas, altitudes, OpenStreetMap) queda en la caché: al repetir, sigue desde ahí."""
    d = _carpeta(pid)
    e = _leer(d, 'estado.json', {})
    fase = e.get('fase')
    if fase not in ('analizando', 'generando'):
        raise ErrorPlan('No hay ningún proceso en marcha en este plan.')
    with open(os.path.join(d, DETENER), 'w', encoding='utf-8') as f:
        f.write(datetime.now().isoformat(timespec='seconds'))
    p = _procesos.get(d)
    if p is not None and p.poll() is None:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
    else:       # proceso de otra VenB: se espera a que lo vea (como mucho, unos segundos)
        for _ in range(30):
            if not en_marcha(d) or not os.path.exists(os.path.join(d, 'latido.txt')):
                break
            time.sleep(0.2)
    try:
        os.remove(os.path.join(d, 'latido.txt'))
    except OSError:
        pass
    _procesos.pop(d, None)
    with open(os.path.join(d, 'registro.txt'), 'a', encoding='utf-8') as f:
        f.write(f'\n== detenido {datetime.now():%d/%m/%Y %H:%M:%S}\n')
    if fase == 'generando':
        _estado(d, fase='listo', error=None, detenido='generar')
    elif os.path.exists(os.path.join(d, 'analisis.json')):
        _estado(d, fase='listo', error=None, detenido='analizar')
    else:
        _estado(d, fase='error', error='Has detenido el análisis. Lo que ya se había descargado queda guardado: '
                                       'vuelve a subir la ruta para seguir desde ahí.')


def estado(pid):
    d = _carpeta(pid)
    e = _leer(d, 'estado.json', {})
    # un proceso que ya no corre (VenB cerrada durante el proceso o fallo grave) no puede seguir «analizando»
    if e.get('fase') in ('analizando', 'generando') and not en_marcha(d):
        e = _leer(d, 'estado.json', {})     # pudo terminar justo ahora
        p = _procesos.get(d)
        if e.get('fase') in ('analizando', 'generando') and (p is None or p.returncode not in (0, None)):
            e = _estado(d, fase='error' if e['fase'] == 'analizando' else 'listo',
                        error='El proceso se interrumpió. Vuelve a intentarlo.' if p is None else 'El proceso terminó con un error.')
    e['id'] = pid
    e['registro'] = registro(d)
    return e


def registro(d, lineas=12):
    try:
        with open(os.path.join(d, 'registro.txt'), encoding='utf-8', errors='replace', newline='') as f:
            texto = f.read()[-20000:]
    except OSError:
        return ''
    # las barras de progreso usan \r: solo cuenta la última versión de cada línea
    filas = [l.split('\r')[-1] for l in texto.split('\n')]
    return '\n'.join(l for l in filas if l.strip())[-3000:].split('\n')[-lineas:]


def enlazar_evento(pid, evento):
    """Une un plan con un evento del calendario de VenB (None lo desune)."""
    _estado(_carpeta(pid), evento=evento)


def lista():
    if not os.path.isdir(PLANES):
        return []
    planes = []
    for pid in sorted(os.listdir(PLANES), reverse=True):
        try:
            e = estado(pid)
        except KeyError:
            continue
        a = _leer(os.path.join(PLANES, pid), 'analisis.json', {}) or {}
        e.update(total_km=a.get('total_km'), total_asc=a.get('total_asc'), salida=(_leer(os.path.join(PLANES, pid), 'parametros.json', {}) or {}).get('salida') or a.get('salida'))
        planes.append(e)
    return planes


def borrar(pid):
    d = _carpeta(pid)
    if en_marcha(d):
        raise ErrorPlan('Este plan se está procesando: espera a que termine.')
    shutil.rmtree(d)


def analisis(pid):
    return _leer(_carpeta(pid), 'analisis.json')


def migrar_parametros(p):
    """Parámetros guardados antes de la 3.58 al formato nuevo. Devuelve (p, cambiado).
    - Tiempo límite personal (`limite_personal`) en brevet, SB o SR: el límite vuelve a ser el oficial; si el personal era
      menor, pasa a tiempo objetivo (recalcula la velocidad); si era mayor, se quita con un aviso.
    - Llegada prevista de Etapas: pasa a tiempo objetivo (horas desde la salida)."""
    if not p:
        return p, False
    cambiado = False
    if 'sin_salida' not in p:
        p.setdefault('sin_salida', False)
        p.setdefault('sin_limite', False)
        p.setdefault('objetivo_h', None)
        p.setdefault('vel_objetivo', False)
        cambiado = True
    if p.get('limite_personal'):
        from generador.datos import LIMITE_SR600, limite_oficial
        mod, dist = p.get('modalidad'), p.get('distancia_brm')
        if mod == 'brevet' and dist == 1200:
            mod = p['modalidad'] = 'sb'
        oficial = LIMITE_SR600 if mod == 'sr' else limite_oficial(dist) if mod in ('brevet', 'sb') and dist else None
        lim = p.get('limite_h')
        if oficial and lim:
            if lim < oficial - 0.01:
                p['objetivo_h'], p['vel_objetivo'] = lim, True
                p['aviso_migracion'] = (f'Este plan tenía un tiempo límite personal de {_hm(lim)}: ahora es el tiempo objetivo, '
                                        f'y el límite vuelve a ser el oficial ({_hm(oficial)}).')
            else:
                p['aviso_migracion'] = (f'Este plan tenía un tiempo límite personal de {_hm(lim)}, mayor que el oficial: '
                                        f'se ha quitado y el límite vuelve a ser el oficial ({_hm(oficial)}).')
            p['limite_h'] = oficial
        p['limite_personal'] = False
        cambiado = True
    p.pop('limite_personal', None)
    e = p.get('etapas') or {}
    if e.get('llegada'):
        try:
            h = (datetime.fromisoformat(e['llegada'][:16]) - datetime.fromisoformat(str(p.get('salida'))[:16])).total_seconds() / 3600
            if h > 0 and not p.get('objetivo_h'):
                p['objetivo_h'], p['vel_objetivo'] = round(h, 4), True
        except (TypeError, ValueError):
            pass
        e['llegada'] = None
        cambiado = True
    return p, cambiado


def _hm(h):
    m = int(round(h * 60))
    return f'{m // 60}:{m % 60:02d} h'


def parametros(pid):
    d = _carpeta(pid)
    p, cambiado = migrar_parametros(_leer(d, 'parametros.json'))
    if cambiado and not en_marcha(d):
        _escribir(d, 'parametros.json', p)
    return p


def ficheros(pid):
    d = os.path.join(_carpeta(pid), 'salida')
    if not os.path.isdir(d):
        return []
    return sorted((f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)) and not f.endswith('.zip')), key=_orden_fichero)


def _orden_fichero(f):
    orden = ['tabla', 'infografia', 'mapa_ilustrado', 'mapa_personal', 'mapa_tronos', 'ruta_interactiva']
    return next((i for i, o in enumerate(orden) if f.startswith(o)), 9), f


TITULOS_DOC = [('tabla', 'Tabla de tiempos'), ('infografia', 'Infografía'), ('mapa_ilustrado', 'Mapa ilustrado (Al-Ballut)'),
               ('mapa_personal', 'Mapa personal'), ('mapa_tronos', 'Mapa «Juego de Tronos»'), ('ruta_interactiva', 'Página interactiva')]
FORMATOS = {'.png': 'PNG', '.pdf': 'PDF', '.xlsx': 'Excel', '.html': 'HTML', '.gpx': 'GPX'}


def documentos(pid):
    """Ficheros generados agrupados por documento (mapa_personal.png y .pdf → «Mapa personal»), en el orden de la página:
    [{'titulo', 'imagen' (PNG para la vista previa o None), 'gpx' (bool), 'ficheros': [(formato, nombre)]}]."""
    grupos = {}
    for f in ficheros(pid):
        base, ext = os.path.splitext(f)
        grupos.setdefault(base, []).append((FORMATOS.get(ext.lower(), ext[1:].upper()), f))
    docs = []
    for base, fs in grupos.items():
        titulo = next((t for k, t in TITULOS_DOC if base.startswith(k)), base)
        if base.startswith('infografia_'):
            titulo += ' ' + base.split('_', 1)[1].replace('_', ' ')
        gpx = base.endswith('_WP') and any(n.endswith('.gpx') for _, n in fs)
        if gpx:
            titulo = 'Ruta con waypoints (GPX)'
        docs.append({'titulo': titulo, 'base': base, 'gpx': gpx, 'imagen': next((n for _, n in fs if n.endswith('.png')), None),
                     'ficheros': sorted(fs, key=lambda x: list(FORMATOS.values()).index(x[0]) if x[0] in FORMATOS.values() else 9)})
    # Arriba, los grandes con vista previa (infografías y mapas); abajo, los pequeños: la ruta con waypoints primero
    return sorted(docs, key=lambda d: (not d['imagen'], not d['gpx']))


def _escribir_gpx(d, plan=None):
    """Escribe salida/<prefijo>_<SALIDA>_WP.gpx con los puntos actuales del plan (los de la hoja y los añadidos a mano).
    Se rehace en cada análisis (también al guardar puntos editados), no solo al generar, para que el GPX descargable
    tenga siempre los últimos waypoints. Sin plan calculado, lo calcula desde el análisis (planes anteriores a la 3.40)."""
    from types import SimpleNamespace
    from generador.web import gpx_waypoints
    a = _leer(d, 'analisis.json')
    p = _leer(d, 'parametros.json') or {}
    if plan is None:
        from generador.datos import calcular, leer_gpx, leer_waypoints, puntos_de_lista
        gpx = os.path.join(d, 'entrada', _leer(d, 'estado.json', {})['gpx'])
        plan = calcular(leer_gpx(gpx), puntos_de_lista(a['puntos']), datetime.now(), a.get('limite_h') or 1, 0, {}, {}, (),
                        'auto', 3.0, '', leer_waypoints(gpx))
    regla = regla_de(p or {'modalidad': a.get('modalidad'), 'distancia_brm': a.get('distancia_brm')})
    nombre, texto = gpx_waypoints(SimpleNamespace(cfg={'regla': regla}), plan)
    salida = os.path.join(d, 'salida')
    os.makedirs(salida, exist_ok=True)
    for viejo in glob.glob(os.path.join(salida, '*_WP.gpx')):
        os.remove(viejo)
    with open(os.path.join(salida, nombre), 'w', encoding='utf-8') as f:
        f.write(texto)


def trazado(pid, paso_m=40):
    """Track del plan para elegir puntos en el mapa: [[lat, lon, km del GPX]] cada `paso_m` como mínimo.
    Los km se cuentan como en generador/datos.leer_gpx (distancia acumulada entre los puntos del fichero)."""
    import xml.etree.ElementTree as ET
    import numpy as np
    from generador.datos import _haversine
    d = _carpeta(pid)
    raiz = ET.parse(os.path.join(d, 'entrada', _leer(d, 'estado.json', {})['gpx'])).getroot()
    pre = raiz.tag.split('}')[0] + '}' if raiz.tag.startswith('{') else ''
    pts = [(float(x.get('lat')), float(x.get('lon'))) for x in raiz.iter(f'{pre}trkpt')] or \
          [(float(x.get('lat')), float(x.get('lon'))) for x in raiz.iter(f'{pre}rtept')]
    if len(pts) < 2:
        return []
    lat, lon = np.array(pts).T
    km = np.concatenate([[0.0], np.cumsum(_haversine(lat[:-1], lon[:-1], lat[1:], lon[1:]))]) / 1000
    salida, ultimo = [], -1.0
    for i in range(len(km)):
        if km[i] - ultimo >= paso_m / 1000 or i == len(km) - 1:
            salida.append([round(float(lat[i]), 5), round(float(lon[i]), 5), round(float(km[i]), 3)])
            ultimo = km[i]
    return salida


def asegurar_gpx(pid):
    """Planes analizados sin GPX con waypoints (anteriores a la 3.40): se crea al abrirlos."""
    d = _carpeta(pid)
    if en_marcha(d) or not _leer(d, 'analisis.json') or glob.glob(os.path.join(d, 'salida', '*_WP.gpx')):
        return
    try:
        _escribir_gpx(d)
    except Exception:
        pass


def fichero(pid, nombre):
    if nombre != os.path.basename(nombre) or nombre.startswith('.'):
        raise KeyError(nombre)
    ruta = os.path.join(_carpeta(pid), 'salida', nombre)
    if not os.path.isfile(ruta):
        raise KeyError(nombre)
    return ruta


def zip_salida(pid):
    d = _carpeta(pid)
    nombre = _nombre_seguro(_leer(d, 'estado.json', {}).get('nombre') or 'ruta', '.zip')
    ruta = os.path.join(d, 'salida', nombre)
    with zipfile.ZipFile(ruta, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in ficheros(pid):
            z.write(os.path.join(d, 'salida', f), f)
    return ruta


MARCA_FICHA = ('const FICHA = false;', 'const FICHA = true;')   # en generador/web.py


def carpeta_web(pid):
    """Nombre limpio de la carpeta para publicar la ruta en una web: «castillo-collados-de-frailes»."""
    d = _carpeta(pid)
    nombre = (_leer(d, 'parametros.json') or {}).get('nombre') or _leer(d, 'estado.json', {}).get('nombre') or 'ruta'
    base = unicodedata.normalize('NFKD', nombre).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', base).strip('-')[:60] or 'ruta'


def codigo_iframe(pid, base_url=None):
    """Código para insertar la ruta en otra web. Sin dirección base (ajuste plan_web_base), con un marcador."""
    base_url = (R.ajustes().get('plan_web_base') if base_url is None else base_url) or ''
    url = (base_url.rstrip('/') + '/' if base_url else 'https://TU-WEB/CARPETA/') + carpeta_web(pid) + '/'
    return (f'<iframe src="{url}" title="Ruta" style="width:100%;height:1200px;border:0" loading="lazy" '
            f'allow="fullscreen"></iframe>\n<p><a href="{url}" target="_blank" rel="noopener">Abrir la ruta a pantalla completa</a></p>')


def exportar_web(pid, ficha=True):
    """ZIP para publicar la página interactiva en una web: <carpeta>/index.html (autónomo: datos y logo dentro) y
    LEEME.txt con el código para insertarla. Con ficha, tiempos desde la salida, sin fecha, cierres ni márgenes."""
    d = _carpeta(pid)
    origen = os.path.join(d, 'salida', 'ruta_interactiva.html')
    if not os.path.isfile(origen):
        raise ErrorPlan('Primero genera la página interactiva (casilla «Página interactiva» y «Generar»).')
    with open(origen, encoding='utf-8') as f:
        html = f.read()
    if ficha:
        if MARCA_FICHA[0] not in html:
            raise ErrorPlan('Esta página interactiva es de una versión anterior de VenB: vuelve a generarla para exportarla como ficha.')
        html = html.replace(MARCA_FICHA[0], MARCA_FICHA[1], 1)
    carpeta = carpeta_web(pid)
    leeme = (f'Ruta para publicar en una web\n\n'
             f'1. Sube la carpeta «{carpeta}» completa a tu alojamiento web (por FTP o con el administrador de archivos), '
             'por ejemplo dentro de una carpeta «rutas».\n'
             f'2. Comprueba que se abre en el navegador: https://tu-web/rutas/{carpeta}/\n'
             '3. Para insertarla en una página o entrada, pega este código en un bloque HTML (en WordPress, bloque «HTML personalizado»), '
             'cambiando la dirección si hace falta:\n\n' + codigo_iframe(pid) + '\n\n'
             'La página es un único fichero: el track, los puntos y el logo van dentro. El mapa base se carga de los servidores '
             'del IGN (España) o de OpenStreetMap/OpenTopoMap, que piden no abusar: para mucho tráfico, mejor el mapa del IGN.\n')
    ruta = os.path.join(d, f'web_{carpeta}.zip')
    with zipfile.ZipFile(ruta, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'{carpeta}/index.html', html)
        z.writestr(f'{carpeta}/LEEME.txt', leeme)
    return ruta


def reglas_rm():
    """Tablas de Randonneurs Mondiaux para la página (la vista previa calcula con ellas, como generador/datos.py)."""
    from generador.datos import APERTURA_BRM, CIERRE_BRM, DISTANCIAS_SB, LIMITE_SR600, MEDIAS_SB, limite_oficial
    return {'limites': {d: limite_oficial(d) for d in DISTANCIAS_BREVET + DISTANCIAS_SB}, 'apertura': APERTURA_BRM, 'cierre': CIERRE_BRM,
            'sr600': LIMITE_SR600, 'brevet': DISTANCIAS_BREVET, 'sb': DISTANCIAS_SB, 'medias_sb': MEDIAS_SB, 'max_etapas': MAX_ETAPAS}


def velocidad_reciente():
    """Velocidad media en movimiento de tus salidas largas en exterior del último año (km/h), o None."""
    try:
        import datos_venb as D
        h = D.historico()
    except Exception:
        return None
    if h is None or not len(h):
        return None
    desde = datetime.now() - timedelta(days=365)
    ext = h[h.bici & ~h.tipo.isin(['Ciclismo virtual', 'Ciclismo en sala']) & (h.fecha >= desde) & (h.h > 0)]
    for minimo in (100, 50):
        s = ext[ext.km >= minimo]
        if len(s) >= 3:
            return {'kmh': round(float(s.km.sum() / s.h.sum()), 1), 'n': int(len(s)), 'km_min': minimo}
    return None


def _club_valido(cid):
    import clubes
    return clubes.club(cid) is not None


def generar(pid, datos):
    """datos: lo enviado por la página (ya validado aquí). Guarda los parámetros y lanza la generación."""
    d = _carpeta(pid)
    if en_marcha(d):
        raise EnMarcha('Este plan ya se está procesando: abajo se ve su progreso.')
    a = _leer(d, 'analisis.json')
    if not a:
        raise ErrorPlan('El plan todavía no está analizado.')
    p = validar(datos, a)
    _escribir(d, 'parametros.json', p)
    _estado(d, fase='generando', nombre=p['nombre'], error=None, aviso_mapas=None, detenido=None, inicio_generar=datetime.now().isoformat(timespec='seconds'))
    _lanzar(d, 'generar')


def validar(datos, a, borrador=False):
    """Parámetros del plan. borrador: al editar los puntos se guarda lo que haya en la página, aunque falte algo."""
    n = len(a['puntos'])

    def num(v, lo, hi, defecto=None):
        try:
            x = float(str(v).replace(',', '.'))
        except (TypeError, ValueError):
            if defecto is not None:
                return defecto
            raise ErrorPlan(f'Valor no válido: {v}')
        if not lo <= x <= hi:
            raise ErrorPlan(f'Valor fuera de rango: {v}')
        return x
    sin_salida, sin_limite = bool(datos.get('sin_salida')), bool(datos.get('sin_limite'))
    try:
        salida = datetime.fromisoformat(str(datos.get('salida', ''))[:16])
    except ValueError:
        if not borrador and not sin_salida:
            raise ErrorPlan('Indica la fecha y la hora de salida, o marca «Sin hora de salida concreta».')
        salida = None
    limite = num(datos.get('limite_h'), 1, 400, 0) or None
    objetivo = num(datos.get('objetivo_h'), 0, 400, 0) or None
    from generador.datos import DISTANCIAS_SB, LIMITE_SR600, limite_oficial
    modalidad = datos.get('modalidad') if datos.get('modalidad') in MODALIDADES else 'libre'
    distancia = None
    try:
        distancia = int(datos.get('distancia_brm'))
    except (TypeError, ValueError):
        distancia = None
    if modalidad == 'brevet' and distancia == 1200:
        modalidad = 'sb'
    validas = {'brevet': DISTANCIAS_BREVET, 'sb': DISTANCIAS_SB, 'sr': [600]}.get(modalidad)
    if validas is None:
        distancia = None
    elif distancia not in validas:
        if modalidad == 'sr':
            distancia = 600
        elif not borrador:
            raise ErrorPlan('Elige la distancia.')
        else:
            distancia = None
    oficial = LIMITE_SR600 if modalidad == 'sr' else limite_oficial(distancia) if distancia else None
    # en las pruebas oficiales el límite es el del reglamento (no se cambia) y el ritmo propio va en el tiempo objetivo,
    # que no puede pasar de él; en el recorrido libre, el tiempo deseado es a la vez límite (columna «Objetivo») y objetivo
    if oficial:
        limite = oficial
        if objetivo and objetivo > oficial + 0.01:
            if not borrador:
                raise ErrorPlan(f'El tiempo objetivo no puede pasar del tiempo límite oficial ({_hm(oficial)}).')
            objetivo = oficial
    else:
        objetivo = limite
        if not limite and not sin_limite and not borrador:
            raise ErrorPlan('Indica el tiempo deseado, o marca «Sin límite de tiempo».')
    e = datos.get('etapas') or {}
    etapas = None
    if e.get('activas') and ver_etapas(modalidad, distancia):
        descanso = num(e.get('descanso_h'), 0, 48, 8)
        # cada parada con su descanso (horas); sin él, el descanso diario
        des = e.get('descansos') or []
        pares = {}
        for j, k in enumerate(e.get('paradas') or []):
            pares[round(num(k, 0, 5000), 3)] = num(des[j] if j < len(des) else None, 0, 48, descanso)
        kms = sorted(pares)[:MAX_ETAPAS - 1]
        etapas = {'activas': True, 'llegada': None, 'descanso_h': descanso, 'paradas': kms, 'descansos': [pares[k] for k in kms]}
    puntos = datos.get('puntos') or []
    if len(puntos) != n:
        raise ErrorPlan('La lista de puntos no coincide con el análisis.')
    pts = [{'mostrar': bool(x.get('mostrar')), 'parada': num(x.get('parada'), 0, 72 * 60, 0),
            'tipo': _tipo(x.get('tipo'))} for x in puntos]
    v = datos.get('velocidades') or {}
    tramos = v.get('tramos') or []
    if not 1 <= len(tramos) <= 20:
        raise ErrorPlan('La tabla de velocidades debe tener entre 1 y 20 tramos.')
    vel = {'tramos': sorted([[num(t[0], -50, 50) / 100, num(t[1], 1, 80)] for t in tramos], key=lambda t: t[0]),
           'resto': num(v.get('resto'), 1, 80), 'fatiga_pct': num(v.get('fatiga_pct'), 0, 50),
           'fatiga_cada': num(v.get('fatiga_cada_pct'), 1, 100) / 100, 'fatiga_max_pct': num(v.get('fatiga_max_pct'), 0, 90),
           'factor': num(v.get('factor'), 0.2, 5)}
    salidas = [s for s in (datos.get('salidas') or []) if s in SALIDAS]
    if not salidas and not borrador:
        raise ErrorPlan('Elige al menos un documento que generar.')
    return {'nombre': ' '.join(str(datos.get('nombre') or a['nombre']).split())[:80] or 'Ruta',
            'subtitulo': ' '.join(str(datos.get('subtitulo') or '').split())[:120],
            'salida': salida.isoformat(timespec='minutes') if salida else None, 'limite_h': limite, 'modalidad': modalidad, 'distancia_brm': distancia,
            'sin_salida': sin_salida, 'sin_limite': sin_limite, 'objetivo_h': objetivo,
            'vel_objetivo': bool(datos.get('vel_objetivo')) and bool(objetivo), 'etapas': etapas,
            'puntos': pts, 'velocidades': vel,
            'salidas': salidas, 'paleta': datos.get('paleta') if datos.get('paleta') in PALETAS else 'verde',
            'estilo_infografia': datos.get('estilo_infografia') if datos.get('estilo_infografia') in ESTILOS_INFOGRAFIA else 'ign_mtn',
            # VenB Rutas: club u organizador cuya marca llevan los documentos ('' = la de VenB)
            'club': datos.get('club') if R.RUTAS and datos.get('club') and _club_valido(datos.get('club')) else '',
            'auto_lugares': bool(datos.get('auto_lugares', True)), 'track_pendiente': bool(datos.get('track_pendiente')), 'servicios': bool(datos.get('servicios', True)), 'altitud_gpx': bool(datos.get('altitud_gpx'))}


def editar_puntos(pid, datos):
    """Guarda los puntos escritos a mano (puntos.json, que manda sobre la hoja) y lo que hubiera en la página
    (paradas, tipos, salida…), alineado con la lista nueva, y vuelve a analizar la ruta."""
    d = _carpeta(pid)
    if en_marcha(d):
        raise ErrorPlan('Este plan se está procesando: espera a que termine.')
    a = _leer(d, 'analisis.json')
    if not a:
        raise ErrorPlan('El plan todavía no está analizado.')
    lista = datos.get('lista') or []
    if not 2 <= len(lista) <= 500:
        raise ErrorPlan('La ruta necesita al menos dos puntos: la salida y la meta.')
    from generador.datos import SI_CONTROL, _id_control, _norm
    puntos = []
    for x in lista:
        nombre = ' '.join(str(x.get('nombre') or '').split())[:80]
        try:
            km = round(float(str(x.get('km')).replace(',', '.')), 3)
        except (TypeError, ValueError):
            raise ErrorPlan(f'Punto «{nombre or "sin nombre"}»: el km no es un número.')
        if not nombre:
            raise ErrorPlan(f'Falta el nombre del punto del km {km:g}.')
        if not 0 <= km <= 5000:
            raise ErrorPlan(f'Punto «{nombre}»: km fuera de rango.')
        bruto = str(x.get('control') or '').strip()[:12]
        control = '?' if _norm(bruto) in SI_CONTROL else (_id_control(bruto) if bruto else '')
        q = {'nombre': nombre, 'km_hoja': km, 'control': control, 'localidad': bool(x.get('localidad', True))}
        for k in ('cierre_hoja', 'apertura_hoja'):    # las horas de la hoja siguen con su punto
            v = x.get(k)
            if v:
                try:
                    q[k] = datetime.fromisoformat(str(v)[:16]).isoformat(timespec='minutes')
                except ValueError:
                    pass
        puntos.append((q, {'mostrar': bool(x.get('mostrar', bool(control))), 'parada': x.get('parada') or 0,
                           'tipo': _tipo(x.get('tipo'))}))
    puntos.sort(key=lambda t: t[0]['km_hoja'])   # orden estable: puntos con el mismo km quedan como estaban
    # Los controles numerados (y los nuevos) se renumeran por orden de km: uno intermedio desplaza a los siguientes.
    # Se empieza en C1 en la salida, salvo que la hoja empiece en C0 (CC Chamartín). Los de letra (CF…) no se tocan.
    numerados = [q for q, _ in puntos if q['control'] == '?' or re.fullmatch(r'C\d+', q['control'])]
    base = 0 if any(q['control'] == 'C0' for q in numerados) else 1
    for n, q in enumerate(numerados):
        q['control'] = f'C{base + n}'
    _escribir(d, 'puntos.json', [q for q, _ in puntos])
    borrador = dict(datos, puntos=[pp for _, pp in puntos])
    try:
        _escribir(d, 'parametros.json', validar(borrador, {'puntos': puntos, 'nombre': a['nombre']}, borrador=True))
    except ErrorPlan:                            # sin parámetros válidos se usan los de partida
        if os.path.exists(os.path.join(d, 'parametros.json')):
            os.remove(os.path.join(d, 'parametros.json'))
    _estado(d, fase='analizando', error=None, detenido=None, inicio_analizar=datetime.now().isoformat(timespec='seconds'))
    _lanzar(d, 'analizar')


def quitar_edicion(pid):
    """Vuelve a los puntos de la hoja de ruta."""
    d = _carpeta(pid)
    if en_marcha(d):
        raise ErrorPlan('Este plan se está procesando: espera a que termine.')
    for f in ('puntos.json', 'parametros.json'):
        if os.path.exists(os.path.join(d, f)):
            os.remove(os.path.join(d, f))
    _estado(d, fase='analizando', error=None, detenido=None, inicio_analizar=datetime.now().isoformat(timespec='seconds'))
    _lanzar(d, 'analizar')


# ------------------------------------------------------------------ trabajo en segundo plano

def _clave(p):
    """Clave con la que el generador reconoce cada punto ("nombre@km de la hoja")."""
    return f"{p['nombre']}@{p['km_hoja']:g}"


def _proyecto(d, cfg):
    from generador.proyecto import Proyecto
    return Proyecto(cfg=cfg, base=d)


def _analizar(d):
    from generador.datos import DISTANCIAS_SB, LIMITES_BRM, Punto, calcular, distancia_nominal, limite_oficial, leer_gpx, leer_hoja, leer_waypoints, puntos_de_lista, velocidades
    e = _leer(d, 'estado.json', {})
    gpx = os.path.join(d, 'entrada', e['gpx'])
    puntos, meta, avisos = [], {}, []
    if e.get('hoja'):
        print('Leyendo la hoja de ruta…', flush=True)
        try:
            puntos, meta = leer_hoja(os.path.join(d, 'entrada', e['hoja']))
            print(f'  {len(puntos)} puntos, {sum(1 for p in puntos if p.control)} controles', flush=True)
        except Exception as ex:   # hoja ilegible: se sigue con el track y los puntos se ponen a mano
            print(f'  no se ha podido leer: {ex}', flush=True)
            avisos.append(f'No se ha podido leer la hoja de ruta ({ex}). Se ha empezado con la salida y la meta del track: '
                          'añade los puntos en la tabla de Previsión («Añadir punto» y «Actualizar los puntos») o sube la ruta con una hoja de cálculo sencilla.')
    editados = _leer(d, 'puntos.json')
    if editados:
        puntos = puntos_de_lista(editados)
        print(f'Puntos editados a mano: {len(puntos)}', flush=True)
    print('Leyendo el track y consultando las altitudes del terreno…', flush=True)
    track = leer_gpx(gpx)
    print(f'  altitudes: {track.fuente_altitud}', flush=True)
    if not puntos:
        puntos = [Punto('Salida', 0.0, 'C1'), Punto('Llegada', round(float(track.total_km), 1), 'C2')]
        if not e.get('hoja'):
            avisos.append('Sin hoja de ruta: el plan empieza con la salida y la meta del track. Añade los puntos y controles en la tabla de Previsión («Añadir punto» y «Actualizar los puntos»).')
    salida = meta.get('salida')
    limite = meta.get('limite_horas')
    plan = calcular(track, puntos, salida or datetime.combine(date.today() + timedelta(days=7), datetime.min.time()).replace(hour=8),
                    limite or 1, 0, {}, {}, (), 'auto', 3.0, '', leer_waypoints(gpx))
    # modalidad propuesta: brevet si la hoja lo dice (distancia oficial u horas de control); si no, recorrido libre
    distancia = meta.get('distancia') if meta.get('distancia') in LIMITES_BRM or meta.get('distancia') in DISTANCIAS_SB else None
    if distancia is None and any(p.cierre_hoja for p in puntos):
        distancia = distancia_nominal(puntos[-1].km_hoja)
    if distancia:   # en un brevet, el límite es el oficial; si la hoja cierra la meta a otra hora, se avisa
        oficial = limite_oficial(distancia)
        if limite and abs(limite - oficial) > 0.01:
            fmt = lambda h: f'{int(h)}:{round(h % 1 * 60):02d}'
            avisos.append(f'La hoja de ruta cierra la meta a las {fmt(limite)} h de la salida, pero el tiempo límite de un BRM de '
                          f'{distancia} km es {fmt(oficial)} h (Randonneurs Mondiaux): se usa el oficial. Los demás controles conservan las horas de la hoja.')
        limite = oficial
    nombre = ' '.join(str(meta.get('nombre') or track.nombre or e.get('nombre') or 'Ruta').split())
    if re.fullmatch(r'(?i)(track|ruta|course)?[\s_0-9-]*', nombre):
        nombre = e.get('nombre') or 'Ruta'
    a = {'nombre': nombre[:80], 'salida': salida.isoformat(timespec='minutes') if salida else None, 'limite_h': limite,
         'modalidad': ('sb' if distancia >= 1200 else 'brevet') if distancia else 'libre',
         'distancia_brm': distancia or (max([x for x in DISTANCIAS_SB if x <= plan.total_km * 1.05] or [1200]) if plan.total_km >= 1140
                                        else distancia_nominal(plan.total_km)),
         'meta': {k: v for k, v in meta.items() if k in ('distancia', 'desnivel', 'club', 'lugar_salida')},
         'total_km': plan.total_km, 'total_asc': plan.total_asc, 'avisos': avisos + plan.avisos, 'anclas': plan.anclas,
         'editados': bool(editados),
         'velocidades': velocidades(), 'perfil': _perfil(track),
         'puntos': [{'nombre': p.nombre, 'control': p.control, 'km_hoja': p.km_hoja, 'km': round(p.km, 3), 'km_tramo': round(p.km_tramo, 3),
                     'alt': round(p.alt), 'asc_tramo': round(p.asc_tramo, 1), 'asc_total': round(p.asc_total), 'pendiente': p.pendiente,
                     'cierre_hoja': p.cierre_hoja.isoformat(timespec='minutes') if p.cierre_hoja else None,
                     'apertura_hoja': p.apertura_hoja.isoformat(timespec='minutes') if p.apertura_hoja else None,
                     'localidad': p.extra.get('localidad', True)} for p in plan.puntos]}
    _escribir(d, 'analisis.json', a)
    try:
        _escribir_gpx(d, plan)
    except Exception as ex:
        print(f'  aviso: no se ha podido preparar el GPX con waypoints ({ex})', flush=True)
    _estado(d, fase='listo', nombre=a['nombre'], error=None)
    print(f'Hecho: {plan.total_km:.1f} km, +{plan.total_asc:.0f} m', flush=True)


def _perfil(track, n=400):
    """Perfil reducido para la vista previa: [km, altitud]."""
    import numpy as np
    i = np.unique(np.linspace(0, len(track.km) - 1, min(n, len(track.km))).astype(int))
    return [[round(float(track.km[j]), 2), round(float(track.ele[j]))] for j in i]


def _aviso_mapas(fallos, motivo):
    """Texto para el plan cuando OpenStreetMap no ha dado todos los datos de los mapas (fallos=None: ninguno).
    fallos: partes que faltan («pueblos») o que faltan en algunas zonas («pueblos (en parte)»)."""
    y = lambda l: ', '.join(l[:-1]) + (' y ' if len(l) > 1 else '') + l[-1]
    enteros = [f for f in fallos or [] if not f.endswith(' (en parte)')]
    partes = [f[:-len(' (en parte)')] for f in fallos or [] if f.endswith(' (en parte)')]
    if not fallos or len(enteros) >= 8:
        que = 'Los mapas se han generado sin datos de OpenStreetMap (ríos, pueblos, cimas, puertos, embalses y servicios junto al track).'
    elif enteros and partes:
        que = f'Faltan datos en los mapas: {y(enteros)} y, en algunas zonas de la ruta, {y(partes)}.'
    elif enteros:
        que = f'Faltan datos en los mapas: {y(enteros)}.'
    else:
        que = f'Faltan datos en algunas zonas de la ruta: {y(partes)}.'
    if motivo and any(x in motivo for x in ('Overpass', 'HTTP', 'imeout', 'onnection')):
        codigo = motivo.replace('Overpass no responde: ', '').replace('Overpass no responde ', '')
        porque = (f'El servidor de OpenStreetMap (Overpass) no respondió ({codigo}): suele ser una saturación pasajera, '
                  'no un problema de la ruta ni de VenB.')
    else:
        porque = f'Falló la descarga ({motivo}).' if motivo else 'Falló la descarga.'
    return (f'{que} {porque} Los documentos sirven, pero los mapas podrían ser más ricos. Lo que sí se descargó queda '
            'guardado: genéralos de nuevo más tarde (dentro de un rato o de unas horas; a primera hora de la mañana el '
            'servidor suele ir mejor) y VenB solo pedirá lo que falta.')


def _generar(d):
    e = _leer(d, 'estado.json', {})
    a = _leer(d, 'analisis.json')
    p, _ = migrar_parametros(_leer(d, 'parametros.json'))
    aj = R.ajustes()
    marca = dict(aj.get('planificador_marca') or {})
    if marca.get('logo') and not os.path.isabs(os.path.expanduser(marca['logo'])):
        marca['logo'] = os.path.join(AQUI, 'generador', 'recursos', marca['logo'])
    marca['logo'] = os.path.expanduser(marca.get('logo') or '') or None
    if not marca['logo']:
        marca.pop('logo')
    if R.RUTAS and p.get('club'):     # VenB Rutas: la marca del club, con la de VenB siempre al lado
        import clubes
        marca = clubes.marca(p['club']) or marca
    paradas = {'por_defecto_min': 0}
    tipos, destacados, sin_caja = {}, [], []
    for pa, pp in zip(a['puntos'], p['puntos']):
        clave = _clave(pa)
        paradas[clave] = pp['parada']
        if _tipo(pp['tipo']):
            tipos[clave] = _tipo(pp['tipo'])
        if pp['mostrar'] and not pa['control']:
            destacados.append(clave)
        if not pp['mostrar'] and pa['control']:
            sin_caja.append(pa['control'])
    estilos = [s for s in ('alballut', 'personal', 'tronos') if s in p['salidas']]
    from generador.datos import limite_oficial
    regla = regla_de(p)
    # Horario de los documentos: sin hora de salida, los tiempos se cuentan desde la salida (+H:MM) y los días son de
    # 24 h; sin límite, sin cierres ni márgenes. El cálculo necesita una salida y un límite: sin ellos se usan la salida
    # de la hoja (sus horas de cierre siguen valiendo) o una cualquiera, y un límite que no se muestra.
    con_salida = bool(p.get('salida')) and not p.get('sin_salida')
    limite = limite_oficial(regla['distancia']) if regla and regla.get('distancia') else p.get('limite_h')
    con_limite = bool(limite) and not p.get('sin_limite')
    puntos = a['puntos']
    if p.get('salida'):         # la escrita, aunque no se muestre
        salida = datetime.fromisoformat(p['salida'])
    elif a.get('salida'):
        salida = datetime.fromisoformat(a['salida'][:16])
    else:                       # ninguna: una cualquiera, y las horas de la hoja no se pueden situar
        salida = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        puntos = [dict(x, cierre_hoja=None, apertura_hoja=None) for x in puntos]
    cfg = {'nombre': p['nombre'], 'subtitulo': p['subtitulo'], 'gpx': f"entrada/{e['gpx']}", 'hoja': None,
           'puntos': puntos, 'meta': a.get('meta') or {},   # los del análisis (leídos o editados): la hoja no se relee
           'salida': salida, 'carpeta_salida': 'salida', 'ajuste_km': 'auto',
           # con la regla de RM, el límite es siempre el oficial (planes guardados antes con el de la hoja)
           'limite_horas': limite or 400,
           'horario': {'salida': con_salida, 'limite': con_limite},
           'regla': regla,
           'destacados': destacados, 'paradas': paradas, 'tipos_parada': tipos, 'velocidades': p['velocidades'],
           'altitud': {'fuente': 'gpx' if p.get('altitud_gpx') else 'mdt'},
           'infografia': {'estilo': p['estilo_infografia'], 'sin_caja': sin_caja, 'track_pendiente': bool(p.get('track_pendiente')),
                          'servicios': p.get('servicios', True)},
           'mapa': {'titulo': p['nombre'], 'estilos': estilos, 'paleta': p['paleta'], 'servicios': p.get('servicios', True)}, 'marca': marca}
    salida_dir = os.path.join(d, 'salida')
    if os.path.isdir(salida_dir):
        shutil.rmtree(salida_dir)
    proyecto = _proyecto(d, cfg)
    print(f'Calculando el plan de {p["nombre"]}…', flush=True)
    plan = proyecto.calcular()
    # puntos que no se mostrarán en los mapas ilustrados (las claves coinciden con las del análisis)
    mostrar = {_clave(pa): pp['mostrar'] for pa, pp in zip(a['puntos'], p['puntos'])}
    for pt in plan.puntos:
        m = mostrar.get(f'{pt.nombre}@{pt.km_hoja:g}')
        pt.extra['mostrar'] = True if m else (None if p['auto_lugares'] else False)
    print(f'  {plan.total_km:.1f} km · +{plan.total_asc:.0f} m · ' + (f'llegada {plan.llegada_final:%d/%m %H:%M}' if con_salida
          else f'tiempo previsto {_hm((plan.llegada_final - plan.salida).total_seconds() / 3600)}'), flush=True)
    from generador.proyecto import exportar_excel
    if 'tabla' in p['salidas']:
        print('Tabla de tiempos…', flush=True)
        exportar_excel(plan, proyecto.salida_dir / 'tabla_tiempos.xlsx')
    osm = None
    aviso_mapas = None
    if 'infografia' in p['salidas'] or estilos:
        from generador.osm import elementos
        tr = plan.track
        print('Datos geográficos: IGN y OpenStreetMap (la primera vez en una zona nueva puede tardar varios minutos)…', flush=True)
        try:
            osm = elementos(tr, (tr.lat.min() - 0.4, tr.lon.min() - 0.6, tr.lat.max() + 0.4, tr.lon.max() + 0.6),
                            servicios=p.get('servicios', True))
            if osm.get('fallos'):
                aviso_mapas = _aviso_mapas(osm['fallos'], osm.get('motivo_fallo'))
        except Exception as ex:
            print(f'  aviso: sin datos geográficos ({ex})', flush=True)
            aviso_mapas = _aviso_mapas(None, str(ex))
        if aviso_mapas:
            print(f'  aviso: {aviso_mapas}', flush=True)
    if 'infografia' in p['salidas']:
        print('Infografías…', flush=True)
        from generador.infografia import generar as g
        g(proyecto, plan, osm)
    if estilos:
        print('Mapas ilustrados…', flush=True)
        from generador.ilustrado import generar as g
        g(proyecto, plan, osm)
    print('Ruta con waypoints (GPX)…', flush=True)
    from generador.web import generar_gpx
    generar_gpx(proyecto, plan)
    if 'web' in p['salidas']:
        print('Página interactiva…', flush=True)
        from generador.web import generar as g
        g(proyecto, plan)
    _estado(d, fase='hecho', error=None, aviso_mapas=aviso_mapas, generado=datetime.now().isoformat(timespec='seconds'))
    print('Hecho.', flush=True)


def _trabajo(orden, d):
    sys.path.insert(0, AQUI)
    import threading

    global _parar_latido
    _parar_latido = threading.Event()

    def latido():
        n = 0
        while not _parar_latido.is_set():
            if os.path.exists(os.path.join(d, DETENER)):
                print('\nDetenido.', flush=True)
                try:
                    os.remove(os.path.join(d, 'latido.txt'))
                except OSError:
                    pass
                os._exit(3)     # el estado lo deja quien lo detuvo (detener)
            if n % LATIDO_S == 0:
                _latir(d)
            n += 1
            _parar_latido.wait(1)
    threading.Thread(target=latido, daemon=True).start()
    try:
        (_analizar if orden == 'analizar' else _generar)(d)
    except Exception as ex:
        import traceback
        traceback.print_exc()
        mensaje = str(ex) or ex.__class__.__name__
        _estado(d, fase='error' if orden == 'analizar' else 'listo', error=mensaje)
        sys.exit(1)
    finally:
        _parar_latido.set()
        try:     # terminado: sin latido, se puede volver a generar enseguida
            os.remove(os.path.join(d, 'latido.txt'))
        except OSError:
            pass


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] not in ('analizar', 'generar'):
        sys.exit(__doc__)
    _trabajo(sys.argv[1], os.path.abspath(sys.argv[2]))
