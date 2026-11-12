"""Versiones nuevas desde GitHub: aviso y botón «Actualizar».
- Comprobar: al arrancar VenB y como mucho cada CADA_H horas (o con «Buscar ahora»), pide a la API pública de GitHub
  la última versión publicada (Releases de `actualizaciones_github`) y busca en ella el ZIP de esta edición:
  VenB-X.YZ.zip o, en VenB Rutas, VenB-X.YZ-Rutas.zip. Sin clave ni cuenta. Cada edición guarda su propio estado
  (~/.venb/actualizacion.json o actualizacion-rutas.json), para que no se pisen si están abiertas a la vez.
- Actualizar (solo desde este ordenador): descarga el ZIP a ~/.venb/actualizar/, comprueba su tamaño y su huella
  SHA-256 (la que publica GitHub), lo descomprime y lanza el instalador de esa versión en modo actualización,
  con la carpeta base de esta instalación. VenB se cierra; el instalador copia la versión nueva junto a VenB-datos,
  rehace el icono, borra la versión anterior y vuelve a abrir VenB. En Linux, en la misma terminal (exec); en Windows,
  en una ventana nueva, porque la carpeta de la versión que se está usando no se puede borrar mientras está abierta.
Ajustes: `actualizaciones_github` (usuario/repositorio; vacío, no se comprueba) y `buscar_actualizaciones` (false: nunca).
VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import rutas  # noqa: E402
from version import VERSION  # noqa: E402

SUFIJO = '-rutas' if rutas.RUTAS else ''
ESTADO = os.path.join(rutas.INTERNO, f'actualizacion{SUFIJO}.json')
TRABAJO = os.path.join(rutas.INTERNO, 'actualizar')
CADA_H = 4
AGENTE = {'User-Agent': 'VenB', 'Accept': 'application/vnd.github+json'}
API = os.environ.get('VENB_GITHUB_API', 'https://api.github.com')   # otra dirección solo para pruebas
_hilo = None
_descarga = {'fase': '', 'error': '', 'hecho': 0, 'total': 0}   # estado de «Actualizar», para la página de espera


def _num(v):
    """'3.30', 'v3.30', '3.30-4-gabc-modificada' -> (3, 30); None si no es una versión."""
    m = re.match(r'v?(\d+)\.(\d+)', str(v or ''))
    return (int(m.group(1)), int(m.group(2))) if m else None


def repositorio(a=None):
    return (a or rutas.ajustes()).get('actualizaciones_github', '')


def url_descargas(a=None):
    r = repositorio(a)
    return f'https://github.com/{r}/releases/latest' if r else ''


def nombre_zip(version):
    return f'VenB-{version}-Rutas.zip' if rutas.RUTAS else f'VenB-{version}.zip'


def ultima_publicada(repo, timeout=15):
    """{'version', 'fichero', 'url', 'tamano', 'sha256', 'pagina'} de la última versión publicada; None si no
    trae el ZIP de esta edición."""
    pet = urllib.request.Request(f'{API}/repos/{repo}/releases/latest', headers=AGENTE)
    with urllib.request.urlopen(pet, timeout=timeout) as r:
        rel = json.load(r)
    n = _num(rel.get('tag_name'))
    if not n:
        return None
    version = f'{n[0]}.{n[1]:02d}'
    for a in rel.get('assets', []):
        if a.get('name') == nombre_zip(version):
            dig = a.get('digest') or ''
            return {'version': version, 'fichero': a['name'], 'url': a['browser_download_url'], 'tamano': a.get('size', 0),
                    'sha256': dig.split(':', 1)[1] if dig.startswith('sha256:') else '', 'pagina': rel.get('html_url', '')}
    return None


def _leer():
    try:
        with open(ESTADO, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _guardar(e):
    os.makedirs(os.path.dirname(ESTADO), exist_ok=True)
    with open(ESTADO + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(e, f, ensure_ascii=False)
    os.replace(ESTADO + '.tmp', ESTADO)


def comprobar():
    """Consulta GitHub y guarda el resultado. Sin conexión, se queda con lo que había y anota el error."""
    a = rutas.ajustes()
    repo = repositorio(a)
    if not repo or not a.get('buscar_actualizaciones', True):
        return None
    e = _leer()
    try:
        r = ultima_publicada(repo)
        e = {'comprobado': time.time(), 'error': '', **(r or {'version': ''})}
    except Exception as x:   # sin red o GitHub no responde: se reintenta más tarde
        e.update(comprobado=time.time(), error=type(x).__name__)
    _guardar(e)
    return e


def en_segundo_plano(forzar=False):
    """Comprueba en un hilo si la última consulta tiene más de CADA_H horas (o con forzar)."""
    global _hilo
    if _hilo and _hilo.is_alive():
        return
    if not forzar and time.time() - _leer().get('comprobado', 0) < CADA_H * 3600:
        return
    _hilo = threading.Thread(target=comprobar, daemon=True)
    _hilo.start()


def buscando():
    return bool(_hilo and _hilo.is_alive())


def estado():
    """Para Acerca de: cuándo se comprobó por última vez, con qué resultado y si se está buscando ahora."""
    e = _leer()
    return {'comprobado': e.get('comprobado'), 'error': e.get('error', ''), 'ultima': e.get('version', ''),
            'buscando': buscando(), 'activo': bool(repositorio()) and rutas.ajustes().get('buscar_actualizaciones', True),
            'pagina': url_descargas()}


def nueva():
    """{'version', 'fichero', 'url', 'pagina'} si en GitHub hay una versión superior a la instalada; None si no."""
    a = rutas.ajustes()
    if not a.get('buscar_actualizaciones', True):
        return None
    e = _leer()
    actual, otra = _num(VERSION), _num(e.get('version'))
    if not actual or not otra or otra <= actual or not e.get('url'):
        return None
    return {'version': e['version'], 'fichero': e.get('fichero', ''), 'url': e['url'], 'pagina': e.get('pagina') or url_descargas(a)}


# ---------------------------------------------------------------- actualizar ---

def base_instalacion():
    """Carpeta que contiene esta versión (VenB-X.YZ) y VenB-datos; None en una copia de desarrollo."""
    base = os.path.dirname(rutas.PROYECTO)
    if not re.fullmatch(re.escape(rutas.PREFIJO_CARPETA) + r'\d+\.\d+', os.path.basename(rutas.PROYECTO)):
        return None
    if os.path.normcase(os.path.abspath(rutas.PERSISTE)) != os.path.normcase(os.path.join(base, rutas.NOMBRE)):
        return None
    return base


def se_puede_actualizar():
    """'' si esta instalación puede actualizarse sola; si no, el motivo."""
    if not base_instalacion():
        return 'esta copia no es una instalación normal (falta la carpeta VenB-X.YZ junto a VenB-datos)'
    if os.name != 'nt' and not shutil.which('bash'):
        return 'no se encuentra bash'
    return ''


def limpiar_restos():
    """Borra lo que quedó de la última actualización (en Windows, el instalador no puede borrarse a sí mismo)."""
    if _descarga['fase'] not in ('descargando', 'descomprimiendo', 'instalando'):
        shutil.rmtree(TRABAJO, ignore_errors=True)


if os.path.isdir(TRABAJO):
    _t = threading.Timer(120, limpiar_restos)
    _t.daemon = True
    _t.start()


def progreso():
    return dict(_descarga)


def _descargar(n, destino):
    pet = urllib.request.Request(n['url'], headers={'User-Agent': 'VenB'})
    h = hashlib.sha256()
    with urllib.request.urlopen(pet, timeout=60) as r, open(destino, 'wb') as f:
        _descarga['total'] = int(r.headers.get('Content-Length') or n.get('tamano') or 0)
        while trozo := r.read(256 * 1024):
            f.write(trozo)
            h.update(trozo)
            _descarga['hecho'] += len(trozo)
    if n.get('tamano') and os.path.getsize(destino) != n['tamano']:
        raise ValueError('la descarga está incompleta')
    if n.get('sha256') and h.hexdigest() != n['sha256']:
        raise ValueError('la huella del fichero descargado no coincide con la publicada')


def _descomprimir(zip_, version):
    """Extrae el ZIP en TRABAJO y devuelve la carpeta del programa; rechaza rutas fuera de su carpeta."""
    raiz = f'{rutas.PREFIJO_CARPETA}{version}/'
    destino = os.path.join(TRABAJO, 'nueva')
    shutil.rmtree(destino, ignore_errors=True)
    with zipfile.ZipFile(zip_) as z:
        for i in z.infolist():
            if not i.filename.startswith(raiz) or '..' in i.filename.split('/') or i.filename.startswith('/'):
                raise ValueError(f'el ZIP tiene un fichero inesperado: {i.filename}')
        z.extractall(destino)
        for i in z.infolist():   # ZIP hecho en Linux: conserva los permisos de los .sh
            if (i.external_attr >> 16) & 0o111 and os.name != 'nt':
                os.chmod(os.path.join(destino, i.filename), 0o755)
    carpeta = os.path.join(destino, raiz.rstrip('/'))
    if not os.path.exists(os.path.join(carpeta, 'venb', 'app.py')):
        raise ValueError('el ZIP no contiene VenB')
    if rutas.RUTAS != os.path.exists(os.path.join(carpeta, 'venb', 'EDICION')):
        raise ValueError('el ZIP es de otra edición')
    return carpeta


def preparar(n):
    """Descarga y descomprime la versión n. Devuelve la carpeta lista para instalar."""
    _descarga.update(fase='descargando', error='', hecho=0, total=n.get('tamano', 0))
    shutil.rmtree(TRABAJO, ignore_errors=True)
    os.makedirs(TRABAJO, exist_ok=True)
    zip_ = os.path.join(TRABAJO, n['fichero'])
    _descargar(n, zip_)
    _descarga['fase'] = 'descomprimiendo'
    carpeta = _descomprimir(zip_, n['version'])
    os.remove(zip_)
    return carpeta


def instalar(carpeta):
    """Cierra VenB y ejecuta el instalador de la versión nueva en modo actualización. No vuelve."""
    base = base_instalacion()
    os.chdir(carpeta)
    env = dict(os.environ, VENB_ACTUALIZAR='1')
    if os.name == 'nt':
        bat = os.path.join(carpeta, 'INSTALAR-EN-WINDOWS.bat')
        # /s y comillas exteriores: cmd solo quita esas, y las rutas con espacios llegan enteras
        subprocess.Popen(f'cmd /s /c ""{bat}" /actualizar "{base}""', cwd=carpeta, env=env,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
        os._exit(0)
    sys.stdout.flush()
    # El servidor web marca su socket como heredable: sin esto, el puerto seguiría ocupado tras el exec
    # y la versión nueva no podría abrirse.
    for fd in os.listdir('/proc/self/fd') if os.path.isdir('/proc/self/fd') else range(3, 256):
        try:
            if int(fd) > 2:
                os.set_inheritable(int(fd), False)
        except (OSError, ValueError):
            pass
    os.execve(shutil.which('bash'), ['bash', os.path.join(carpeta, 'instalar-en-linux.sh'), '--actualizar', base], env)


def actualizar():
    """En segundo plano: prepara la versión nueva y, si todo va bien, cierra VenB e instala."""
    n = nueva()
    if not n or _descarga['fase'] in ('descargando', 'descomprimiendo', 'instalando'):
        return False

    def tarea():
        try:
            carpeta = preparar(n)
        except Exception as x:
            _descarga.update(fase='error', error=str(x) or type(x).__name__)
            return
        _descarga['fase'] = 'instalando'
        time.sleep(2)          # la página de espera recibe el cambio de fase antes de que VenB se cierre
        try:
            instalar(carpeta)
        except Exception as x:
            _descarga.update(fase='error', error=f'no se ha podido lanzar el instalador: {x}')
    threading.Thread(target=tarea, daemon=True).start()
    return True
