"""Freno de los inicios de sesión en Garmin Connect, para no provocar bloqueos por exceso de intentos.

Garmin (Cloudflare) bloquea durante horas la IP que inicia sesión demasiadas veces (error 1015 o 429, «rate limited»),
y el bloqueo afecta también al navegador. Tras un fallo de inicio de sesión, los intentos automáticos (al arrancar VenB,
cada pocas horas, el equipo de las bicis y la descarga diaria) esperan cada vez más: 30 min, 2 h, 6 h y 24 h como máximo,
también después de cerrar y reabrir VenB. Los intentos a mano (botones) son como mucho 3 por hora. Un inicio de sesión
correcto lo pone todo a cero.

Estado en ~/.venb/garmin_bloqueo.json (en Windows, %USERPROFILE%\\.venb). Solo biblioteca estándar: lo usan VenB y
scripts/garmin_diario.py, que se ejecuta con el Python de garmindb.
"""
import json
import os
import re
from datetime import datetime, timedelta

RUTA = os.path.join(os.path.expanduser('~'), '.venb', 'garmin_bloqueo.json')
ESPERAS_H = [0.5, 2, 6, 24]      # tras el 1.º, 2.º, 3.º y 4.º fallo seguido (y siguientes)
MANUALES_POR_HORA = 3

MENSAJES = {
    'bloqueo': 'Garmin ha bloqueado temporalmente el acceso desde tu conexión por demasiados intentos de inicio de sesión. '
               'Espera unas horas sin intentarlo (tampoco desde el navegador). Después, comprueba tu correo y contraseña '
               'entrando en connect.garmin.com, mejor desde el móvil con datos móviles.',
    'clave': 'Garmin Connect no ha aceptado el usuario o la contraseña: revísalos en Ajustes (y entra en connect.garmin.com '
             'para comprobarlos).',
    'mfa': 'Tu cuenta de Garmin tiene la verificación en dos pasos: VenB no puede conectarse así. Desactívala en Garmin Connect '
           'o descarga tus actividades a mano.',
    'red': 'Garmin Connect no responde o no hay conexión a Internet.',
    'otro': 'No se ha podido iniciar sesión en Garmin Connect.',
}


def clasificar(texto):
    """Tipo de fallo a partir de un mensaje o un registro: 'bloqueo', 'mfa', 'clave', 'red', 'otro' o None (sin fallo)."""
    t = texto or ''
    if re.search(r'\b1015\b|\b429\b|rate.?limit|TooManyRequests|Too Many Requests|bloqueado temporalmente', t, re.I):
        return 'bloqueo'
    if re.search(r'MFA|two.?factor|verificaci[oó]n en dos pasos|c[oó]digo de verificaci', t, re.I):
        return 'mfa'
    if re.search(r'\b401\b|\b403\b|Unauthorized|Auth\w*Error|usuario y la contrase|Failed to login|Invalid.*(password|credentials)', t, re.I):
        return 'clave'
    if re.search(r'ConnectionError|Max retries|Timeout|no responde|Name or service not known|getaddrinfo', t, re.I):
        return 'red'
    if re.search(r'Traceback|HTTPError|Error', t):
        return 'otro'
    return None


def _leer():
    try:
        with open(RUTA, encoding='utf-8') as f:
            e = json.load(f)
        return e if isinstance(e, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar(e):
    os.makedirs(os.path.dirname(RUTA), exist_ok=True)
    with open(RUTA + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(e, f, ensure_ascii=False, indent=1)
    os.replace(RUTA + '.tmp', RUTA)


def _fecha(x):
    try:
        return datetime.fromisoformat(x)
    except (TypeError, ValueError):
        return None


def estado():
    """{'fallos', 'ultimo' (datetime), 'tipo', 'motivo', 'auto_hasta', 'manual_hasta'} (hasta = None si se puede ya)."""
    e, ahora = _leer(), datetime.now()
    fallos, ultimo = int(e.get('fallos') or 0), _fecha(e.get('ultimo'))
    auto = None
    if fallos and ultimo:
        auto = ultimo + timedelta(hours=ESPERAS_H[min(fallos, len(ESPERAS_H)) - 1])
        if auto <= ahora:
            auto = None
    recientes = sorted(t for t in (_fecha(x) for x in e.get('manuales', [])) if t and ahora - t < timedelta(hours=1))
    manual = recientes[0] + timedelta(hours=1) if len(recientes) >= MANUALES_POR_HORA else None
    # tras un bloqueo de Garmin, tampoco a mano hasta que pase la primera espera
    if e.get('tipo') == 'bloqueo' and auto and (not manual or manual < auto):
        manual = auto
    return {'fallos': fallos, 'ultimo': ultimo, 'tipo': e.get('tipo'), 'motivo': e.get('motivo'),
            'auto_hasta': auto, 'manual_hasta': manual}


def puede(manual=False):
    """(se puede intentar ya, motivo si no). Un intento a mano que se permite queda contado."""
    e = estado()
    hasta = e['manual_hasta'] if manual else e['auto_hasta']
    if hasta:
        cuando = f"{hasta:%H:%M}" + ('' if hasta.date() == datetime.now().date() else f' del {hasta:%d/%m/%Y}')
        if manual and not (e['fallos'] and e['auto_hasta']):
            motivo = f'Ya has hecho {MANUALES_POR_HORA} intentos de conexión con Garmin en la última hora.'
        else:
            motivo = MENSAJES.get(e['tipo'] or 'otro', MENSAJES['otro'])
        quien = 'podrás volver a intentarlo' if manual else 'VenB no lo volverá a intentar sola hasta'
        return False, (f"{motivo} Para no provocar un bloqueo de Garmin, {quien} a partir de las {cuando}." if manual
                       else f"{motivo} Para no provocar un bloqueo de Garmin, {quien} las {cuando}.")
    if manual:
        d = _leer()
        ahora = datetime.now()
        d['manuales'] = [x for x in d.get('manuales', []) if (_fecha(x) or ahora) > ahora - timedelta(hours=1)] + [ahora.isoformat(timespec='seconds')]
        _guardar(d)
    return True, None


def registrar(ok, texto=''):
    """Resultado de un intento: ok pone el contador a cero; un fallo de inicio de sesión suma uno. Los fallos que no son
    de inicio de sesión (p. ej., una actividad que no existe) no cuentan. Devuelve el tipo de fallo o None."""
    d = _leer()
    if ok:
        if d.get('fallos'):
            d.update(fallos=0, tipo=None, motivo=None)
            _guardar(d)
        return None
    tipo = clasificar(texto) or 'otro'
    d.update(fallos=int(d.get('fallos') or 0) + 1, ultimo=datetime.now().isoformat(timespec='seconds'), tipo=tipo,
             motivo=(texto or '')[-300:])
    _guardar(d)
    return tipo


def nueva_clave():
    """Al guardar otro usuario o contraseña, se puede probar ya (salvo si Garmin ha bloqueado la conexión)."""
    d = _leer()
    if d.get('fallos') and d.get('tipo') != 'bloqueo':
        d.update(fallos=0, tipo=None, motivo=None)
        _guardar(d)


def aviso():
    """Texto para Inicio y Ajustes si hay un fallo reciente sin resolver, o None."""
    e = estado()
    if not e['fallos']:
        return None
    texto = MENSAJES.get(e['tipo'] or 'otro', MENSAJES['otro'])
    if e['auto_hasta']:
        texto += f" VenB no volverá a intentarlo sola hasta las {e['auto_hasta']:%H:%M}" + \
            ('' if e['auto_hasta'].date() == datetime.now().date() else f" del {e['auto_hasta']:%d/%m/%Y}") + '.'
    return texto
