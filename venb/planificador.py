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
MODALIDADES = {'brevet': 'Brevet (BRM)', 'sr': 'Super Randonnée', 'libre': 'Recorrido libre'}
TIPOS_PARADA = {'': '—', 'salida': 'Salida', 'cafe': 'Café', 'comida': 'Comida', 'dormir': 'Dormir', 'agua': 'Agua', 'cruce': 'Cruce', 'peligro': 'Peligro',
                'interes': 'Punto de interés', 'llegada': 'Llegada', 'otra': 'Otra'}
PALETAS = ['verde', 'acuarela', 'bosque', 'pizarra', 'alballut']
ESTILOS_INFOGRAFIA = {'ign_mtn': 'IGN: topográfico (MTN)', 'ign_base': 'IGN Base', 'ign_orto': 'IGN: ortofoto con rótulos',
                      'topo': 'Topográfico (OpenStreetMap)', 'osm': 'OpenStreetMap', 'hot': 'Humanitario (OpenStreetMap)'}
_procesos = {}


class ErrorPlan(Exception):
    pass


# ------------------------------------------------------------------ planes guardados

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
    _estado(d, fase='analizando', creado=datetime.now().isoformat(timespec='seconds'), gpx=rg, hoja=rh,
            nombre=os.path.splitext(gpx.filename)[0][:80], gpx_original=os.path.basename(gpx.filename)[:120],
            hoja_original=os.path.basename(hoja.filename)[:120] if hoja else '', evento=evento)
    _lanzar(d, 'analizar')
    return pid


def _lanzar(d, orden):
    """Proceso aparte, con su registro; sobrevive a la petición, no a VenB (se marca como interrumpido)."""
    log = open(os.path.join(d, 'registro.txt'), 'a', encoding='utf-8')
    log.write(f'\n== {orden} {datetime.now():%d/%m/%Y %H:%M:%S}\n')
    log.flush()
    opciones = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), orden, d], stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         cwd=AQUI, env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1', GENERADOR_CACHE=CACHE, MPLBACKEND='Agg'), **opciones)
    log.close()
    _procesos[d] = p


def en_marcha(d):
    p = _procesos.get(d)
    return p is not None and p.poll() is None


def estado(pid):
    d = _carpeta(pid)
    e = _leer(d, 'estado.json', {})
    # un proceso que ya no corre (VenB reiniciada o fallo grave) no puede seguir «analizando»
    if e.get('fase') in ('analizando', 'generando') and not en_marcha(d):
        p = _procesos.get(d)
        if p is None or p.returncode not in (0, None):
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


def parametros(pid):
    return _leer(_carpeta(pid), 'parametros.json')


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
    modalidad, dist = p.get('modalidad', a.get('modalidad')), p.get('distancia_brm', a.get('distancia_brm'))
    regla = {'distancia': dist} if modalidad == 'brevet' and dist else None
    nombre, texto = gpx_waypoints(SimpleNamespace(cfg={'regla': regla}), plan)
    salida = os.path.join(d, 'salida')
    os.makedirs(salida, exist_ok=True)
    for viejo in glob.glob(os.path.join(salida, '*_WP.gpx')):
        os.remove(viejo)
    with open(os.path.join(salida, nombre), 'w', encoding='utf-8') as f:
        f.write(texto)


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


def reglas_rm():
    """Tablas de Randonneurs Mondiaux para la página (la vista previa calcula con ellas, como generador/datos.py)."""
    from generador.datos import APERTURA_BRM, CIERRE_BRM, LIMITE_SR600, LIMITES_BRM
    return {'limites': LIMITES_BRM, 'apertura': APERTURA_BRM, 'cierre': CIERRE_BRM, 'sr600': LIMITE_SR600}


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
        raise ErrorPlan('Este plan ya se está procesando.')
    a = _leer(d, 'analisis.json')
    if not a:
        raise ErrorPlan('El plan todavía no está analizado.')
    p = validar(datos, a)
    _escribir(d, 'parametros.json', p)
    _estado(d, fase='generando', nombre=p['nombre'], error=None)
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
    try:
        salida = datetime.fromisoformat(str(datos.get('salida', ''))[:16])
    except ValueError:
        if not borrador:
            raise ErrorPlan('Indica la fecha y la hora de salida.')
        salida = None
    limite = num(datos.get('limite_h'), 1, 400, None if not borrador else 0) or None
    from generador.datos import LIMITES_BRM
    modalidad = datos.get('modalidad') if datos.get('modalidad') in MODALIDADES else 'libre'
    distancia = None
    if modalidad == 'brevet':
        try:
            distancia = int(datos.get('distancia_brm'))
        except (TypeError, ValueError):
            distancia = None
        if distancia not in LIMITES_BRM:
            if not borrador:
                raise ErrorPlan('Elige la distancia del brevet.')
            distancia = None
    puntos = datos.get('puntos') or []
    if len(puntos) != n:
        raise ErrorPlan('La lista de puntos no coincide con el análisis.')
    pts = [{'mostrar': bool(x.get('mostrar')), 'parada': num(x.get('parada'), 0, 72 * 60, 0),
            'tipo': x.get('tipo') if x.get('tipo') in TIPOS_PARADA else ''} for x in puntos]
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
            'puntos': pts, 'velocidades': vel,
            'salidas': salidas, 'paleta': datos.get('paleta') if datos.get('paleta') in PALETAS else 'verde',
            'estilo_infografia': datos.get('estilo_infografia') if datos.get('estilo_infografia') in ESTILOS_INFOGRAFIA else 'ign_mtn',
            # VenB Rutas: club u organizador cuya marca llevan los documentos ('' = la de VenB)
            'club': datos.get('club') if R.RUTAS and datos.get('club') and _club_valido(datos.get('club')) else '',
            'auto_lugares': bool(datos.get('auto_lugares', True)), 'track_pendiente': bool(datos.get('track_pendiente')), 'altitud_gpx': bool(datos.get('altitud_gpx'))}


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
                           'tipo': x.get('tipo') if x.get('tipo') in TIPOS_PARADA else ''}))
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
    _estado(d, fase='analizando', error=None)
    _lanzar(d, 'analizar')


def quitar_edicion(pid):
    """Vuelve a los puntos de la hoja de ruta."""
    d = _carpeta(pid)
    if en_marcha(d):
        raise ErrorPlan('Este plan se está procesando: espera a que termine.')
    for f in ('puntos.json', 'parametros.json'):
        if os.path.exists(os.path.join(d, f)):
            os.remove(os.path.join(d, f))
    _estado(d, fase='analizando', error=None)
    _lanzar(d, 'analizar')


# ------------------------------------------------------------------ trabajo en segundo plano

def _clave(p):
    """Clave con la que el generador reconoce cada punto ("nombre@km de la hoja")."""
    return f"{p['nombre']}@{p['km_hoja']:g}"


def _proyecto(d, cfg):
    from generador.proyecto import Proyecto
    return Proyecto(cfg=cfg, base=d)


def _analizar(d):
    from generador.datos import LIMITES_BRM, Punto, calcular, distancia_nominal, leer_gpx, leer_hoja, leer_waypoints, puntos_de_lista, velocidades
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
                          'añade los puntos en la tabla de Previsión («Añadir punto» y «Actualizar») o sube la ruta con una hoja de cálculo sencilla.')
    editados = _leer(d, 'puntos.json')
    if editados:
        puntos = puntos_de_lista(editados)
        print(f'Puntos editados a mano: {len(puntos)}', flush=True)
    print('Leyendo el track y consultando las altitudes del terreno…', flush=True)
    track = leer_gpx(gpx)
    if not puntos:
        puntos = [Punto('Salida', 0.0, 'C1'), Punto('Meta', round(float(track.total_km), 1), 'C2')]
        if not e.get('hoja'):
            avisos.append('Sin hoja de ruta: el plan empieza con la salida y la meta del track. Añade los puntos y controles en la tabla de Previsión («Añadir punto» y «Actualizar»).')
    salida = meta.get('salida')
    limite = meta.get('limite_horas')
    plan = calcular(track, puntos, salida or datetime.combine(date.today() + timedelta(days=7), datetime.min.time()).replace(hour=8),
                    limite or 1, 0, {}, {}, (), 'auto', 3.0, '', leer_waypoints(gpx))
    # modalidad propuesta: brevet si la hoja lo dice (distancia oficial u horas de control); si no, recorrido libre
    distancia = meta.get('distancia') if meta.get('distancia') in LIMITES_BRM else None
    if distancia is None and any(p.cierre_hoja for p in puntos):
        distancia = distancia_nominal(puntos[-1].km_hoja)
    if distancia:   # en un brevet, el límite es el oficial; si la hoja cierra la meta a otra hora, se avisa
        oficial = LIMITES_BRM[distancia]
        if limite and abs(limite - oficial) > 0.01:
            fmt = lambda h: f'{int(h)}:{round(h % 1 * 60):02d}'
            avisos.append(f'La hoja de ruta cierra la meta a las {fmt(limite)} h de la salida, pero el tiempo límite de un BRM de '
                          f'{distancia} km es {fmt(oficial)} h (Randonneurs Mondiaux): se usa el oficial. Los demás controles conservan las horas de la hoja.')
        limite = oficial
    nombre = ' '.join(str(meta.get('nombre') or track.nombre or e.get('nombre') or 'Ruta').split())
    if re.fullmatch(r'(?i)(track|ruta|course)?[\s_0-9-]*', nombre):
        nombre = e.get('nombre') or 'Ruta'
    a = {'nombre': nombre[:80], 'salida': salida.isoformat(timespec='minutes') if salida else None, 'limite_h': limite,
         'modalidad': 'brevet' if distancia else 'libre', 'distancia_brm': distancia or distancia_nominal(plan.total_km),
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


def _generar(d):
    from generador.datos import LIMITES_BRM
    e = _leer(d, 'estado.json', {})
    a = _leer(d, 'analisis.json')
    p = _leer(d, 'parametros.json')
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
        if pp['tipo']:
            tipos[clave] = pp['tipo']
        if pp['mostrar'] and not pa['control']:
            destacados.append(clave)
        if not pp['mostrar'] and pa['control']:
            sin_caja.append(pa['control'])
    estilos = [s for s in ('alballut', 'personal', 'tronos') if s in p['salidas']]
    cfg = {'nombre': p['nombre'], 'subtitulo': p['subtitulo'], 'gpx': f"entrada/{e['gpx']}", 'hoja': None,
           'puntos': a['puntos'], 'meta': a.get('meta') or {},   # los del análisis (leídos o editados): la hoja no se relee
           'salida': datetime.fromisoformat(p['salida']), 'carpeta_salida': 'salida', 'ajuste_km': 'auto',
           # en un brevet, el límite es siempre el oficial (planes guardados antes con el de la hoja)
           'limite_horas': LIMITES_BRM[p['distancia_brm']] if p.get('modalidad') == 'brevet' and p.get('distancia_brm') in LIMITES_BRM else p['limite_h'],
           'regla': {'distancia': p['distancia_brm']} if p.get('modalidad') == 'brevet' and p.get('distancia_brm') else None,
           'destacados': destacados, 'paradas': paradas, 'tipos_parada': tipos, 'velocidades': p['velocidades'],
           'altitud': {'fuente': 'gpx' if p.get('altitud_gpx') else 'mdt'},
           'infografia': {'estilo': p['estilo_infografia'], 'sin_caja': sin_caja, 'track_pendiente': bool(p.get('track_pendiente'))},
           'mapa': {'titulo': p['nombre'], 'estilos': estilos, 'paleta': p['paleta']}, 'marca': marca}
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
    print(f'  {plan.total_km:.1f} km · +{plan.total_asc:.0f} m · llegada {plan.llegada_final:%d/%m %H:%M}', flush=True)
    from generador.proyecto import exportar_excel
    if 'tabla' in p['salidas']:
        print('Tabla de tiempos…', flush=True)
        exportar_excel(plan, proyecto.salida_dir / 'tabla_tiempos.xlsx')
    osm = None
    if 'infografia' in p['salidas'] or estilos:
        from generador.osm import elementos
        tr = plan.track
        print('Datos geográficos: IGN y OpenStreetMap (la primera vez en una zona nueva puede tardar varios minutos)…', flush=True)
        try:
            osm = elementos(tr, (tr.lat.min() - 0.4, tr.lon.min() - 0.6, tr.lat.max() + 0.4, tr.lon.max() + 0.6))
        except Exception as ex:
            print(f'  aviso: sin datos geográficos ({ex})', flush=True)
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
    _estado(d, fase='hecho', error=None, generado=datetime.now().isoformat(timespec='seconds'))
    print('Hecho.', flush=True)


def _trabajo(orden, d):
    sys.path.insert(0, AQUI)
    try:
        (_analizar if orden == 'analizar' else _generar)(d)
    except Exception as ex:
        import traceback
        traceback.print_exc()
        mensaje = str(ex) or ex.__class__.__name__
        _estado(d, fase='error' if orden == 'analizar' else 'listo', error=mensaje)
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] not in ('analizar', 'generar'):
        sys.exit(__doc__)
    _trabajo(sys.argv[1], os.path.abspath(sys.argv[2]))
