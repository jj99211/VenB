"""Acceso a VenB desde otros equipos de la red local (móvil, tablet), protegido con una clave.
Desactivado por defecto: entonces VenB solo escucha en 127.0.0.1. La clave se guarda cifrada (hash) en ~/.venb/red_clave,
y la clave de las sesiones del navegador, en ~/.venb/red_sesion; ninguna entra en las copias de seguridad.
VenB © José A. Jiménez (https://www.vivirenbici.es). Licencia CC BY-NC-SA 4.0."""
import hashlib
import ipaddress
import os
import secrets
import socket
import threading
import time
from werkzeug.security import check_password_hash, generate_password_hash
import rutas as R

CLAVE = os.path.join(R.INTERNO, 'red_clave')
SESION = os.path.join(R.INTERNO, 'red_sesion')
MIN_CLAVE = 6
MAX_FALLOS = 5          # fallos seguidos antes de bloquear la entrada
BLOQUEO_S = 10 * 60
_fallos = {'n': 0, 'hasta': 0.0}
_cerrojo = threading.Lock()


def _escribir_privado(ruta, texto):
    os.makedirs(R.INTERNO, mode=0o700, exist_ok=True)
    with open(ruta + '.tmp', 'w', encoding='utf-8') as f:
        f.write(texto)
    try:
        os.chmod(ruta + '.tmp', 0o600)
    except OSError:
        pass
    os.replace(ruta + '.tmp', ruta)


def _hash_guardado():
    try:
        with open(CLAVE, encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


def tiene_clave():
    return bool(_hash_guardado())


def activada():
    """Solo se abre a la red si el usuario lo ha pedido y hay clave."""
    return bool(R.ajustes().get('red_local')) and tiene_clave()


def host_escucha():
    return '0.0.0.0' if activada() else '127.0.0.1'


def guardar_clave(clave):
    if len(clave) < MIN_CLAVE or len(clave) > 100:
        raise ValueError(f'La clave debe tener al menos {MIN_CLAVE} caracteres.')
    _escribir_privado(CLAVE, generate_password_hash(clave))


def marca_clave():
    """Cambia al cambiar la clave: así las sesiones abiertas con la anterior dejan de valer."""
    return hashlib.sha256(_hash_guardado().encode()).hexdigest()[:16]


def clave_sesion():
    try:
        with open(SESION, encoding='utf-8') as f:
            k = f.read().strip()
        if k:
            return k
    except OSError:
        pass
    k = secrets.token_hex(32)
    _escribir_privado(SESION, k)
    return k


def comprobar(clave):
    """Devuelve (correcta, mensaje de error). Tras varios fallos seguidos bloquea la entrada un rato."""
    with _cerrojo:
        ahora = time.time()
        if _fallos['hasta'] > ahora:
            return False, f'Demasiados intentos. Vuelve a probar dentro de {int((_fallos["hasta"] - ahora) // 60) + 1} min.'
        h = _hash_guardado()
        if h and check_password_hash(h, clave):
            _fallos['n'] = 0
            return True, ''
        _fallos['n'] += 1
        if _fallos['n'] >= MAX_FALLOS:
            _fallos['n'] = 0
            _fallos['hasta'] = ahora + BLOQUEO_S
            return False, f'Clave incorrecta. Entrada bloqueada {BLOQUEO_S // 60} min.'
        return False, 'Clave incorrecta.'


def es_local(ip):
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def es_red_privada(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private and not a.is_loopback


def host_valido(host, puerto):
    """El nombre con que se pide la página debe ser una IP: impide que una web ajena llegue a VenB por un nombre suyo."""
    nombre, _, p = host.rpartition(':')
    if p != str(puerto):
        return False
    try:
        ipaddress.ip_address(nombre.strip('[]'))
        return True
    except ValueError:
        return False


def ip_local():
    """IP de este ordenador en la red local (no envía nada: solo elige la interfaz de salida)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except OSError:
        ip = ''
    finally:
        s.close()
    return ip if es_red_privada(ip) else ''


def direccion(puerto):
    ip = ip_local()
    return f'http://{ip}:{puerto}' if ip else ''
